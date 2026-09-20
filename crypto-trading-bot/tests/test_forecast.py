import numpy as np
import pandas as pd

from bot.forecast import evaluate_forecast, linear_trend_forecast


def make_df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"close": prices}, index=idx)


def test_linear_trend_forecast_extrapolates_a_perfect_line():
    history = np.array([100.0, 101.0, 102.0, 103.0, 104.0])  # +1/day
    forecast = linear_trend_forecast(history, horizon=3)
    assert abs(forecast - 107.0) < 1e-6  # 104 + 1*3


def test_evaluate_forecast_on_pure_uptrend_favors_the_model():
    # A clean straight-line uptrend is the best possible case for linear extrapolation.
    prices = [100 + i for i in range(120)]
    df = make_df(prices)
    result = evaluate_forecast(df, window=20, horizon=5)

    assert result.num_predictions > 0
    assert result.model_mae < result.naive_mae  # trend model should win here
    assert result.model_direction_accuracy_pct == 100.0  # trend never reverses


def test_evaluate_forecast_on_random_walk_does_not_reliably_beat_naive():
    # Random walk is the textbook case where no model should have a real edge.
    rng = np.random.default_rng(42)
    steps = rng.normal(0, 1, 300)
    prices = 100 + np.cumsum(steps)
    df = make_df(prices.tolist())
    result = evaluate_forecast(df, window=20, horizon=5)

    # Directional accuracy on a true random walk should hover near a coin flip (50%),
    # not be reliably and substantially above it.
    assert 30 < result.model_direction_accuracy_pct < 70


def test_evaluate_forecast_raises_when_not_enough_data():
    df = make_df([100.0] * 10)
    try:
        evaluate_forecast(df, window=20, horizon=5)
        assert False, "expected ValueError"
    except ValueError:
        pass
