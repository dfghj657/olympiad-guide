from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bot.risk import (
    RiskParams,
    is_stop_loss_safe,
    liquidation_price,
    margin_required,
    position_size,
    stop_loss_price,
    take_profit_price,
)
from bot.strategies.base import Strategy


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    return_pct: float


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list = field(default_factory=list)

    @property
    def total_return_pct(self) -> float:
        return (self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1) * 100

    @property
    def max_drawdown_pct(self) -> float:
        running_max = self.equity_curve.cummax()
        drawdown = (self.equity_curve - running_max) / running_max
        return drawdown.min() * 100

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def num_liquidations(self) -> int:
        return sum(1 for t in self.trades if t.exit_reason == "liquidation")

    @property
    def win_rate_pct(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.return_pct > 0)
        return wins / len(self.trades) * 100

    @property
    def avg_trade_return_pct(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.return_pct for t in self.trades) / len(self.trades)

    @property
    def sharpe_ratio(self) -> float:
        returns = self.equity_curve.pct_change().dropna()
        if returns.std() == 0 or len(returns) < 2:
            return 0.0
        periods_per_year = 365 * 24  # assumes hourly candles; informative, not exact
        return (returns.mean() / returns.std()) * np.sqrt(periods_per_year)

    def summary(self) -> dict:
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "num_trades": self.num_trades,
            "num_liquidations": self.num_liquidations,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "avg_trade_return_pct": round(self.avg_trade_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    risk: RiskParams,
    initial_capital: float = 1000.0,
) -> BacktestResult:
    positions = strategy.generate_positions(df)

    equity = initial_capital
    equity_curve = pd.Series(index=df.index, dtype=float)
    trades: list[Trade] = []

    in_position = False
    entry_price = 0.0
    entry_time = None
    qty = 0.0
    margin = 0.0
    sl_price = 0.0
    tp_price = 0.0
    liq_price = 0.0

    fee_mult = risk.fee_pct / 100

    for i, (ts, row) in enumerate(df.iterrows()):
        if not in_position:
            equity_curve.iloc[i] = equity
            if positions.iloc[i] == 1:
                entry_price = row["close"] * (1 + fee_mult)
                qty = position_size(equity, entry_price, risk)
                if qty > 0:
                    in_position = True
                    entry_time = ts
                    margin = margin_required(qty, entry_price, risk)
                    sl_price = stop_loss_price(entry_price, risk)
                    tp_price = take_profit_price(entry_price, risk)
                    liq_price = liquidation_price(entry_price, risk)
            continue

        exit_price = None
        exit_reason = None

        # Liquidation is an exchange-forced close, not our own order — if it sits
        # closer to entry than our stop-loss, it fires first as price falls.
        liquidated = risk.leverage > 1 and liq_price > 0 and row["low"] <= liq_price
        stopped = row["low"] <= sl_price

        if liquidated and (not stopped or liq_price >= sl_price):
            exit_reason = "liquidation"
        elif stopped:
            exit_price = sl_price
            exit_reason = "stop_loss"
        elif row["high"] >= tp_price:
            exit_price = tp_price
            exit_reason = "take_profit"
        elif positions.iloc[i] == 0:
            exit_price = row["close"]
            exit_reason = "signal"

        if exit_reason == "liquidation":
            # Full margin for this trade is gone; nothing left to take a fee from.
            equity -= margin
            trades.append(Trade(entry_time, entry_price, ts, liq_price, "liquidation", -100.0))
            in_position = False
        elif exit_price is not None:
            exit_price_after_fee = exit_price * (1 - fee_mult)
            dollar_pnl = qty * (exit_price_after_fee - entry_price)
            equity += dollar_pnl
            trade_return_pct = (dollar_pnl / margin) * 100 if margin > 0 else 0.0
            trades.append(Trade(entry_time, entry_price, ts, exit_price_after_fee, exit_reason, trade_return_pct))
            in_position = False

        equity_curve.iloc[i] = equity

    return BacktestResult(equity_curve=equity_curve, trades=trades)


__all__ = ["Trade", "BacktestResult", "run_backtest", "is_stop_loss_safe"]
