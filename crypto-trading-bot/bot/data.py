import time

import pandas as pd
import ccxt


def fetch_ohlcv_range(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch historical OHLCV candles in pages until `until_ms` is reached."""
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    all_candles = []
    cursor = since_ms

    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        all_candles.extend(batch)
        last_ts = batch[-1][0]
        next_cursor = last_ts + timeframe_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < limit:
            break
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df[df["timestamp"] < until_ms]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").set_index("timestamp").sort_index()
    return df


def fetch_recent_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.set_index("timestamp").sort_index()
