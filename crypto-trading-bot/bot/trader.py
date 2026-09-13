import csv
import json
import time
from pathlib import Path

import ccxt
import pandas as pd

from bot.logger import setup_logger
from bot.risk import RiskParams, position_size, stop_loss_price, take_profit_price
from bot.strategies.base import Strategy

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
logger = setup_logger()


def _state_path(symbol: str, dry_run: bool) -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    tag = "paper" if dry_run else "live"
    return STATE_DIR / f"{tag}_{symbol.replace('/', '-')}.json"


def _trades_csv_path(symbol: str, dry_run: bool) -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    tag = "paper" if dry_run else "live"
    return STATE_DIR / f"{tag}_{symbol.replace('/', '-')}_trades.csv"


def _load_state(path: Path, initial_capital: float) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {
        "in_position": False,
        "entry_price": 0.0,
        "qty": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "balance": initial_capital,
    }


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2))


def _log_trade(path: Path, row: dict) -> None:
    is_new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def run_iteration(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    strategy: Strategy,
    risk: RiskParams,
    dry_run: bool,
    initial_capital: float,
) -> dict:
    limit = strategy.warmup_periods + 50
    candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp").sort_index()

    closed = df.iloc[:-1]  # drop the still-forming candle
    if len(closed) < strategy.warmup_periods:
        logger.warning("Not enough candles yet for warmup (%d/%d)", len(closed), strategy.warmup_periods)
        return {"action": "wait"}

    positions = strategy.generate_positions(closed)
    signal = int(positions.iloc[-1])
    last_close = float(closed["close"].iloc[-1])

    state_path = _state_path(symbol, dry_run)
    trades_path = _trades_csv_path(symbol, dry_run)
    state = _load_state(state_path, initial_capital)

    action = "hold"

    if not state["in_position"]:
        should_buy = signal == 1
        if should_buy:
            balance = state["balance"] if dry_run else exchange.fetch_balance()["free"][symbol.split("/")[1]]
            qty = position_size(balance, last_close, risk)
            if qty > 0:
                entry_price = last_close * (1 + risk.fee_pct / 100)
                if dry_run:
                    state["balance"] -= qty * entry_price
                else:
                    exchange.create_market_buy_order(symbol, qty)
                state.update({
                    "in_position": True,
                    "entry_price": entry_price,
                    "qty": qty,
                    "stop_loss": stop_loss_price(entry_price, risk),
                    "take_profit": take_profit_price(entry_price, risk),
                })
                action = "buy"
                logger.info("BUY %s qty=%.6f price=%.2f", symbol, qty, entry_price)
    else:
        hit_stop = last_close <= state["stop_loss"]
        hit_target = last_close >= state["take_profit"]
        should_sell = signal == 0 or hit_stop or hit_target

        if should_sell:
            exit_price = last_close * (1 - risk.fee_pct / 100)
            qty = state["qty"]
            if dry_run:
                state["balance"] += qty * exit_price
            else:
                exchange.create_market_sell_order(symbol, qty)

            reason = "stop_loss" if hit_stop else "take_profit" if hit_target else "signal"
            return_pct = (exit_price / state["entry_price"] - 1) * 100
            _log_trade(trades_path, {
                "timestamp": pd.Timestamp.utcnow().isoformat(),
                "symbol": symbol,
                "entry_price": state["entry_price"],
                "exit_price": exit_price,
                "qty": qty,
                "reason": reason,
                "return_pct": round(return_pct, 3),
            })
            logger.info("SELL %s qty=%.6f price=%.2f reason=%s return=%.2f%%", symbol, qty, exit_price, reason, return_pct)

            state.update({"in_position": False, "entry_price": 0.0, "qty": 0.0, "stop_loss": 0.0, "take_profit": 0.0})
            action = "sell"

    _save_state(state_path, state)
    return {"action": action, "signal": signal, "price": last_close, "state": state}


def run_forever(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    strategy: Strategy,
    risk: RiskParams,
    dry_run: bool,
    initial_capital: float,
    once: bool = False,
    poll_interval_sec: int | None = None,
) -> None:
    mode = "PAPER" if dry_run else "LIVE"
    logger.info("Starting %s trading: %s %s strategy=%s", mode, symbol, timeframe, strategy.name)

    interval = poll_interval_sec or exchange.parse_timeframe(timeframe)

    while True:
        try:
            run_iteration(exchange, symbol, timeframe, strategy, risk, dry_run, initial_capital)
        except Exception:
            logger.exception("Error during trading iteration")

        if once:
            break
        time.sleep(interval)
