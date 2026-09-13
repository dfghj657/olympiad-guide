import pandas as pd

from bot.strategies.base import Strategy


class SmaCrossoverStrategy(Strategy):
    """Long while the fast SMA is above the slow SMA, flat otherwise."""

    name = "sma"

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.warmup_periods = slow_period

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        fast_sma = df["close"].rolling(self.fast_period).mean()
        slow_sma = df["close"].rolling(self.slow_period).mean()
        position = (fast_sma > slow_sma).astype(int)
        position.iloc[: self.warmup_periods] = 0
        return position
