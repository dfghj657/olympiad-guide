import base64
import io
import threading
import webbrowser
from collections import deque
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, url_for

from bot.backtest import run_backtest
from bot.data import fetch_ohlcv_range
from bot.exchange import build_public_exchange
from bot.risk import RiskParams
from bot.strategies import build_strategy
from bot.trader import _trades_csv_path, run_iteration

app = Flask(__name__)

STRATEGY_LABELS = {"sma": "SMA (трендовая)", "rsi": "RSI (контртрендовая)"}


def make_strategy(form):
    name = form.get("strategy", "sma")
    if name == "sma":
        return build_strategy("sma", fast_period=int(form.get("fast", 20)), slow_period=int(form.get("slow", 50)))
    return build_strategy(
        "rsi",
        period=int(form.get("rsi_period", 14)),
        buy_threshold=float(form.get("rsi_buy", 30)),
        sell_threshold=float(form.get("rsi_sell", 70)),
    )


def make_risk(form):
    return RiskParams(
        risk_per_trade_pct=float(form.get("risk_pct", 1.0)),
        stop_loss_pct=float(form.get("stop_loss_pct", 2.0)),
        take_profit_pct=float(form.get("take_profit_pct", 4.0)),
        fee_pct=float(form.get("fee_pct", 0.1)),
    )


def equity_chart_base64(equity_curve: pd.Series) -> str:
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(equity_curve.index, equity_curve.values, color="#2563eb", linewidth=1.6)
    ax.set_title("Баланс во времени (бэктест)")
    ax.set_ylabel("USDT")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


DEFAULT_FORM = {
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "strategy": "sma",
    "fast": 20,
    "slow": 50,
    "rsi_period": 14,
    "rsi_buy": 30,
    "rsi_sell": 70,
    "risk_pct": 1.0,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0,
    "fee_pct": 0.1,
    "capital": 1000,
    "date_from": "2023-01-01",
    "date_to": "2024-01-01",
    "interval_sec": 60,
}


@app.route("/")
def index():
    return redirect(url_for("backtest"))


@app.route("/backtest", methods=["GET", "POST"])
def backtest():
    result = None
    error = None
    form_values = dict(DEFAULT_FORM)

    if request.method == "POST":
        form_values.update(request.form.to_dict())
        try:
            exchange = build_public_exchange()
            since_ms = int(
                datetime.strptime(form_values["date_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000
            )
            until_ms = int(
                datetime.strptime(form_values["date_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000
            )
            df = fetch_ohlcv_range(exchange, form_values["symbol"], form_values["timeframe"], since_ms, until_ms)
            if df.empty:
                error = "Не удалось получить исторические данные. Проверьте символ, таймфрейм и даты."
            else:
                strategy = make_strategy(form_values)
                risk = make_risk(form_values)
                capital = float(form_values["capital"])
                bt_result = run_backtest(df, strategy, risk, initial_capital=capital)
                buy_hold_pct = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
                result = {
                    "summary": bt_result.summary(),
                    "buy_hold_pct": round(buy_hold_pct, 2),
                    "chart": equity_chart_base64(bt_result.equity_curve),
                    "num_candles": len(df),
                    "period_start": df.index[0],
                    "period_end": df.index[-1],
                    "trades": list(reversed(bt_result.trades))[:20],
                }
        except Exception as exc:  # surfaced to the user in the page, not a 500
            error = f"Ошибка: {exc}"

    return render_template(
        "backtest.html", form=form_values, result=result, error=error, strategy_labels=STRATEGY_LABELS
    )


class PaperSession:
    def __init__(self):
        self.thread = None
        self.stop_event = threading.Event()
        self.running = False
        self.config = None
        self.log = deque(maxlen=100)
        self.lock = threading.Lock()

    def start(self, symbol, timeframe, strategy, risk, capital, interval_sec):
        with self.lock:
            if self.running:
                return False
            self.stop_event.clear()
            self.config = {
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy": strategy.name,
                "capital": capital,
            }
            self.running = True

        def loop():
            exchange = build_public_exchange()
            while not self.stop_event.is_set():
                entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                try:
                    entry.update(run_iteration(exchange, symbol, timeframe, strategy, risk, True, capital))
                except Exception as exc:
                    entry.update({"action": "error", "error": str(exc)})
                self.log.appendleft(entry)
                self.stop_event.wait(interval_sec)
            with self.lock:
                self.running = False

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self.running = False


paper_session = PaperSession()


@app.route("/paper")
def paper():
    trades = []
    if paper_session.config:
        path = _trades_csv_path(paper_session.config["symbol"], True)
        if path.exists():
            trades = pd.read_csv(path).tail(30).iloc[::-1].to_dict("records")
    return render_template(
        "paper.html",
        session=paper_session,
        trades=trades,
        form=DEFAULT_FORM,
        strategy_labels=STRATEGY_LABELS,
    )


@app.route("/paper/start", methods=["POST"])
def paper_start():
    strategy = make_strategy(request.form)
    risk = make_risk(request.form)
    symbol = request.form.get("symbol", "BTC/USDT")
    timeframe = request.form.get("timeframe", "1h")
    capital = float(request.form.get("capital", 1000))
    interval_sec = int(request.form.get("interval_sec", 60))
    paper_session.start(symbol, timeframe, strategy, risk, capital, interval_sec)
    return redirect(url_for("paper"))


@app.route("/paper/stop", methods=["POST"])
def paper_stop():
    paper_session.stop()
    return redirect(url_for("paper"))


@app.route("/paper/status.json")
def paper_status_json():
    return jsonify(
        {
            "running": paper_session.running,
            "config": paper_session.config,
            "log": list(paper_session.log)[:20],
        }
    )


def main():
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
