import numpy as np
import pandas as pd

from bot.strategies.base import Strategy


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


class RsiStrategy(Strategy):
    """Buy when RSI recovers above `buy_threshold` from oversold, sell above `sell_threshold`."""

    name = "rsi"

    def __init__(self, period: int = 14, buy_threshold: float = 30, sell_threshold: float = 70):
        if buy_threshold >= sell_threshold:
            raise ValueError("buy_threshold must be smaller than sell_threshold")
        self.period = period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.warmup_periods = period + 1

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        rsi = compute_rsi(df["close"], self.period)
        prev_rsi = rsi.shift(1)

        buy_signal = (prev_rsi < self.buy_threshold) & (rsi >= self.buy_threshold)
        sell_signal = (prev_rsi > self.sell_threshold) & (rsi <= self.sell_threshold)

        position = np.zeros(len(df), dtype=int)
        in_position = False
        buy_arr = buy_signal.to_numpy()
        sell_arr = sell_signal.to_numpy()

        for i in range(len(df)):
            if i < self.warmup_periods:
                position[i] = 0
                continue
            if not in_position and buy_arr[i]:
                in_position = True
            elif in_position and sell_arr[i]:
                in_position = False
            position[i] = int(in_position)

        return pd.Series(position, index=df.index)
