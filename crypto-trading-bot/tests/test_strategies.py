import numpy as np
import pandas as pd

from bot.risk import RiskParams, position_size
from bot.strategies.rsi_strategy import RsiStrategy, compute_rsi
from bot.strategies.sma_crossover import SmaCrossoverStrategy


def make_df(prices):
    n = len(prices)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "open": prices,
        "high": [p * 1.001 for p in prices],
        "low": [p * 0.999 for p in prices],
        "close": prices,
        "volume": [1.0] * n,
    }, index=idx)


def test_sma_crossover_goes_long_on_uptrend():
    prices = list(range(1, 101))  # steady uptrend
    df = make_df(prices)
    strategy = SmaCrossoverStrategy(fast_period=5, slow_period=10)
    positions = strategy.generate_positions(df)

    assert positions.iloc[:10].sum() == 0  # warmup period stays flat
    assert positions.iloc[-1] == 1  # fast SMA above slow SMA on a steady uptrend


def test_sma_crossover_rejects_invalid_periods():
    try:
        SmaCrossoverStrategy(fast_period=50, slow_period=20)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_rsi_goes_long_after_bounce_from_oversold():
    # Sharp drop then recovery should push RSI below 30 then back above it.
    prices = [100] * 20 + list(np.linspace(100, 60, 15)) + list(np.linspace(60, 90, 15))
    df = make_df(prices)
    strategy = RsiStrategy(period=14, buy_threshold=30, sell_threshold=70)
    positions = strategy.generate_positions(df)

    rsi = compute_rsi(df["close"], period=14)
    assert rsi.min() < 30  # confirms the drop actually created an oversold condition
    assert positions.sum() > 0  # strategy entered a long position at some point


def test_position_size_respects_risk_budget():
    risk = RiskParams(risk_per_trade_pct=1.0, stop_loss_pct=2.0)
    qty = position_size(balance=1000, entry_price=100, risk=risk)

    loss_if_stopped_out = qty * (100 - 100 * 0.98)
    assert abs(loss_if_stopped_out - 10) < 1e-6  # 1% of 1000 balance


def test_position_size_never_exceeds_balance():
    risk = RiskParams(risk_per_trade_pct=50.0, stop_loss_pct=0.1)
    qty = position_size(balance=1000, entry_price=100, risk=risk)
    assert qty * 100 <= 1000 + 1e-6
