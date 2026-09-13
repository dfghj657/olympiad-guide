from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """A strategy turns an OHLCV DataFrame into a 'position' column: 1 = long, 0 = flat."""

    name: str
    warmup_periods: int

    @abstractmethod
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        ...
