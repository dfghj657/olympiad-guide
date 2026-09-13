from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bot.risk import RiskParams, stop_loss_price, take_profit_price
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
    sl_price = 0.0
    tp_price = 0.0

    fee_mult = risk.fee_pct / 100

    for i, (ts, row) in enumerate(df.iterrows()):
        if not in_position:
            equity_curve.iloc[i] = equity
            if positions.iloc[i] == 1:
                in_position = True
                entry_price = row["close"] * (1 + fee_mult)
                entry_time = ts
                sl_price = stop_loss_price(entry_price, risk)
                tp_price = take_profit_price(entry_price, risk)
            continue

        exit_price = None
        exit_reason = None

        if row["low"] <= sl_price:
            exit_price = sl_price
            exit_reason = "stop_loss"
        elif row["high"] >= tp_price:
            exit_price = tp_price
            exit_reason = "take_profit"
        elif positions.iloc[i] == 0:
            exit_price = row["close"]
            exit_reason = "signal"

        if exit_price is not None:
            exit_price_after_fee = exit_price * (1 - fee_mult)
            trade_return_pct = (exit_price_after_fee / entry_price - 1) * 100
            equity *= exit_price_after_fee / entry_price
            trades.append(Trade(entry_time, entry_price, ts, exit_price_after_fee, exit_reason, trade_return_pct))
            in_position = False

        equity_curve.iloc[i] = equity

    return BacktestResult(equity_curve=equity_curve, trades=trades)
