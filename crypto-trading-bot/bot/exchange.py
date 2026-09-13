import ccxt

from bot.config import ExchangeConfig


def build_exchange(config: ExchangeConfig) -> ccxt.Exchange:
    exchange_class = getattr(ccxt, config.exchange_id)
    exchange = exchange_class({
        "apiKey": config.api_key,
        "secret": config.api_secret,
        "enableRateLimit": True,
    })
    if config.use_testnet:
        exchange.set_sandbox_mode(True)
    return exchange


def build_public_exchange(exchange_id: str = "binance") -> ccxt.Exchange:
    """Exchange instance for read-only calls (historical data, no keys needed)."""
    exchange_class = getattr(ccxt, exchange_id)
    return exchange_class({"enableRateLimit": True})
