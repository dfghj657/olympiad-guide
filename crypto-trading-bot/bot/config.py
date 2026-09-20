import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ExchangeConfig:
    exchange_id: str
    api_key: str
    api_secret: str
    use_testnet: bool
    market_type: str = "spot"  # "spot" or "futures"

    @classmethod
    def from_env(cls) -> "ExchangeConfig":
        return cls(
            exchange_id=os.getenv("EXCHANGE_ID", "binance"),
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            use_testnet=os.getenv("USE_TESTNET", "true").lower() in ("1", "true", "yes"),
            market_type=os.getenv("MARKET_TYPE", "spot").lower(),
        )
