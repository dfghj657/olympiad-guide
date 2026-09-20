from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ForecastEvalResult:
    num_predictions: int
    model_mae: float
    model_mape: float
    naive_mae: float
    naive_mape: float
    model_direction_accuracy_pct: float
    samples: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "num_predictions": self.num_predictions,
            "model_mae": round(self.model_mae, 2),
            "model_mape_pct": round(self.model_mape, 2),
            "naive_mae": round(self.naive_mae, 2),
            "naive_mape_pct": round(self.naive_mape, 2),
            "model_beats_naive": self.model_mape < self.naive_mape,
            "model_direction_accuracy_pct": round(self.model_direction_accuracy_pct, 2),
        }


def linear_trend_forecast(history: np.ndarray, horizon: int) -> float:
    """Fit a straight line through `history` and project it `horizon` steps past its end."""
    x = np.arange(len(history))
    slope, intercept = np.polyfit(x, history, 1)
    return float(slope * (len(history) - 1 + horizon) + intercept)


def evaluate_forecast(df: pd.DataFrame, window: int, horizon: int) -> ForecastEvalResult:
    """Walk-forward evaluation: at every point in history, forecast `horizon` bars ahead
    using only the `window` bars before it, then compare against what actually happened.

    Also computes a "naive" baseline that just predicts tomorrow's price will equal
    today's (a classic hard-to-beat benchmark in finance) — a model claiming skill has
    to actually beat this, not just produce a number.
    """
    closes = df["close"].to_numpy()
    n = len(closes)

    model_errors, naive_errors = [], []
    model_pct_errors, naive_pct_errors = [], []
    direction_hits = 0
    total = 0
    samples = []

    last_i = n - horizon
    for i in range(window, last_i + 1):
        history = closes[i - window:i]
        current_price = closes[i - 1]
        actual_future = closes[i + horizon - 1]

        model_pred = linear_trend_forecast(history, horizon)
        naive_pred = current_price

        model_errors.append(abs(model_pred - actual_future))
        naive_errors.append(abs(naive_pred - actual_future))
        model_pct_errors.append(abs(model_pred - actual_future) / actual_future * 100)
        naive_pct_errors.append(abs(naive_pred - actual_future) / actual_future * 100)

        if (actual_future > current_price) == (model_pred > current_price):
            direction_hits += 1
        total += 1

        samples.append({
            "time": df.index[i + horizon - 1],
            "actual": float(actual_future),
            "model_forecast": float(model_pred),
            "naive_forecast": float(naive_pred),
        })

    if total == 0:
        raise ValueError("Not enough candles for this window/horizon combination.")

    return ForecastEvalResult(
        num_predictions=total,
        model_mae=float(np.mean(model_errors)),
        model_mape=float(np.mean(model_pct_errors)),
        naive_mae=float(np.mean(naive_errors)),
        naive_mape=float(np.mean(naive_pct_errors)),
        model_direction_accuracy_pct=direction_hits / total * 100,
        samples=samples,
    )
