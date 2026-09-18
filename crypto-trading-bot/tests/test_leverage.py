import pandas as pd

from bot.backtest import run_backtest
from bot.risk import (
    RiskParams,
    is_stop_loss_safe,
    liquidation_price,
    margin_required,
    position_size,
)
from bot.strategies.base import Strategy


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


class BuyAndHoldOnce(Strategy):
    """Enters long on the first bar and never exits on its own signal."""

    name = "buy_and_hold_once"
    warmup_periods = 0

    def generate_positions(self, df):
        return pd.Series([1] * len(df), index=df.index)


def test_liquidation_price_no_leverage_means_no_extra_risk():
    risk = RiskParams(leverage=1.0)
    assert liquidation_price(100.0, risk) == 0.0


def test_liquidation_price_moves_closer_to_entry_as_leverage_rises():
    low_leverage = liquidation_price(100.0, RiskParams(leverage=2.0))
    high_leverage = liquidation_price(100.0, RiskParams(leverage=20.0))
    # Higher leverage means liquidation sits closer to the entry price.
    assert high_leverage > low_leverage


def test_is_stop_loss_safe_when_stop_is_tighter_than_liquidation():
    risk = RiskParams(stop_loss_pct=2.0, leverage=5.0)  # liquidation ~ 19.5% away
    assert is_stop_loss_safe(risk) is True


def test_is_stop_loss_safe_false_when_leverage_makes_liquidation_hit_first():
    risk = RiskParams(stop_loss_pct=5.0, leverage=50.0)  # liquidation ~ 1.5% away
    assert is_stop_loss_safe(risk) is False


def test_margin_required_scales_inversely_with_leverage():
    qty = 1.0
    margin_1x = margin_required(qty, 100.0, RiskParams(leverage=1.0))
    margin_10x = margin_required(qty, 100.0, RiskParams(leverage=10.0))
    assert margin_1x == 100.0
    assert abs(margin_10x - 10.0) < 1e-9


def test_position_size_unaffected_by_leverage_for_same_stop_loss():
    # Leverage changes margin required, not the dollar-risk-based quantity.
    qty_1x = position_size(1000, 100, RiskParams(risk_per_trade_pct=1.0, stop_loss_pct=2.0, leverage=1.0))
    qty_10x = position_size(1000, 100, RiskParams(risk_per_trade_pct=1.0, stop_loss_pct=2.0, leverage=10.0))
    assert abs(qty_1x - qty_10x) < 1e-9


def test_backtest_liquidates_before_stop_loss_at_high_leverage():
    # 20x leverage -> liquidation ~4.5% away, tighter than the 10% stop-loss below.
    prices = [100.0, 100.0, 90.0, 90.0, 90.0]
    df = make_df(prices)
    strategy = BuyAndHoldOnce()
    risk = RiskParams(risk_per_trade_pct=100.0, stop_loss_pct=10.0, take_profit_pct=50.0, fee_pct=0.0, leverage=20.0)

    result = run_backtest(df, strategy, risk, initial_capital=1000.0)

    assert result.num_liquidations == 1
    liquidation_trades = [t for t in result.trades if t.exit_reason == "liquidation"]
    assert liquidation_trades[0].return_pct == -100.0


def test_backtest_stop_loss_still_fires_first_at_safe_leverage():
    # 2x leverage -> liquidation ~49.5% away, far looser than the 10% stop-loss.
    prices = [100.0, 100.0, 88.0, 88.0, 88.0]
    df = make_df(prices)
    strategy = BuyAndHoldOnce()
    risk = RiskParams(risk_per_trade_pct=100.0, stop_loss_pct=10.0, take_profit_pct=50.0, fee_pct=0.0, leverage=2.0)

    result = run_backtest(df, strategy, risk, initial_capital=1000.0)

    assert result.num_liquidations == 0
    assert result.trades[0].exit_reason == "stop_loss"
