from dataclasses import dataclass


@dataclass
class RiskParams:
    risk_per_trade_pct: float = 1.0   # % of balance risked per trade
    stop_loss_pct: float = 2.0        # distance to stop-loss from entry
    take_profit_pct: float = 4.0      # distance to take-profit from entry
    fee_pct: float = 0.1              # taker fee per side, e.g. Binance spot 0.1%


def position_size(balance: float, entry_price: float, risk: RiskParams) -> float:
    """Quantity to buy so that hitting the stop-loss loses `risk_per_trade_pct` of balance."""
    risk_amount = balance * (risk.risk_per_trade_pct / 100)
    stop_loss_price = entry_price * (1 - risk.stop_loss_pct / 100)
    loss_per_unit = entry_price - stop_loss_price
    if loss_per_unit <= 0:
        return 0.0
    qty = risk_amount / loss_per_unit
    max_affordable_qty = balance / entry_price
    return min(qty, max_affordable_qty)


def stop_loss_price(entry_price: float, risk: RiskParams) -> float:
    return entry_price * (1 - risk.stop_loss_pct / 100)


def take_profit_price(entry_price: float, risk: RiskParams) -> float:
    return entry_price * (1 + risk.take_profit_pct / 100)
