from bot.strategies.rsi_strategy import RsiStrategy
from bot.strategies.sma_crossover import SmaCrossoverStrategy

STRATEGIES = {
    "sma": SmaCrossoverStrategy,
    "rsi": RsiStrategy,
}


def build_strategy(name: str, **kwargs):
    if name not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGIES)}")
    return STRATEGIES[name](**kwargs)
