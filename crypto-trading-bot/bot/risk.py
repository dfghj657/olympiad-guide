from dataclasses import dataclass

# Real exchanges also require maintenance margin on top of the raw 1/leverage
# distance, so actual liquidation happens slightly closer to entry than our
# estimate here. Treat liquidation_price() as an optimistic approximation,
# never as an exact figure to plan around.
MAINTENANCE_MARGIN_BUFFER_PCT = 0.5


@dataclass
class RiskParams:
    risk_per_trade_pct: float = 1.0   # % of balance risked per trade
    stop_loss_pct: float = 2.0        # distance to stop-loss from entry
    take_profit_pct: float = 4.0      # distance to take-profit from entry
    fee_pct: float = 0.1              # taker fee per side, e.g. Binance spot 0.1%
    leverage: float = 1.0             # 1.0 = spot / no leverage


def position_size(balance: float, entry_price: float, risk: RiskParams) -> float:
    """Quantity so that hitting the stop-loss loses `risk_per_trade_pct` of balance.

    This is independent of leverage: leverage only changes how much margin is
    needed to hold this quantity (see margin_required), not the dollar risk.
    """
    risk_amount = balance * (risk.risk_per_trade_pct / 100)
    sl_price = stop_loss_price(entry_price, risk)
    loss_per_unit = entry_price - sl_price
    if loss_per_unit <= 0:
        return 0.0
    qty = risk_amount / loss_per_unit
    max_affordable_qty = (balance * risk.leverage) / entry_price
    return min(qty, max_affordable_qty)


def margin_required(qty: float, entry_price: float, risk: RiskParams) -> float:
    """Capital that must actually be posted to open this position."""
    return qty * entry_price / risk.leverage


def stop_loss_price(entry_price: float, risk: RiskParams) -> float:
    return entry_price * (1 - risk.stop_loss_pct / 100)


def take_profit_price(entry_price: float, risk: RiskParams) -> float:
    return entry_price * (1 + risk.take_profit_pct / 100)


def liquidation_price(entry_price: float, risk: RiskParams) -> float:
    """Approximate long-position liquidation price under `risk.leverage`.

    At leverage L, losing the full margin means the price moved against you
    by roughly 1/L. Real exchanges liquidate a bit earlier than this because
    they also require maintenance margin and fees — treat this as the
    optimistic edge, not a guarantee.
    """
    if risk.leverage <= 1:
        return 0.0  # no leverage, no liquidation risk beyond losing the trade itself
    move_pct = (1 / risk.leverage) * 100 - MAINTENANCE_MARGIN_BUFFER_PCT
    move_pct = max(move_pct, 0.0)
    return entry_price * (1 - move_pct / 100)


def is_stop_loss_safe(risk: RiskParams) -> bool:
    """False when liquidation would trigger before the configured stop-loss.

    At high leverage the exchange can force-close (and wipe the position's
    margin) before your own stop-loss order ever gets the chance to fire.
    """
    if risk.leverage <= 1:
        return True
    liq = liquidation_price(100.0, risk)  # scale-free: use 100 as a stand-in price
    liq_move_pct = (100.0 - liq) / 100.0 * 100
    return risk.stop_loss_pct < liq_move_pct
