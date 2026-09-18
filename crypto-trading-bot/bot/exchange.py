import ccxt

from bot.config import ExchangeConfig

# ccxt's unified API expects a per-exchange "defaultType" to reach derivatives
# markets. Most exchanges call perpetual contracts "swap"; Binance calls its
# USDT-margined perpetuals "future". This mapping is not exhaustive — verify
# on an exchange you haven't used here before trusting it.
FUTURES_DEFAULT_TYPE = {
    "binance": "future",
}
DEFAULT_FUTURES_TYPE = "swap"


def _default_type(exchange_id: str, market_type: str) -> str:
    if market_type == "spot":
        return "spot"
    return FUTURES_DEFAULT_TYPE.get(exchange_id, DEFAULT_FUTURES_TYPE)


def build_exchange(config: ExchangeConfig) -> ccxt.Exchange:
    exchange_class = getattr(ccxt, config.exchange_id)
    exchange = exchange_class({
        "apiKey": config.api_key,
        "secret": config.api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": _default_type(config.exchange_id, config.market_type)},
    })
    if config.use_testnet:
        exchange.set_sandbox_mode(True)
    return exchange


def build_public_exchange(exchange_id: str = "binance", market_type: str = "spot") -> ccxt.Exchange:
    """Exchange instance for read-only calls (historical data, no keys needed)."""
    exchange_class = getattr(ccxt, exchange_id)
    return exchange_class({
        "enableRateLimit": True,
        "options": {"defaultType": _default_type(exchange_id, market_type)},
    })


def futures_symbol(symbol: str) -> str:
    """Convert a spot symbol like BTC/USDT into ccxt's unified perpetual-swap form."""
    if ":" in symbol:
        return symbol
    base, quote = symbol.split("/")
    return f"{base}/{quote}:{quote}"
