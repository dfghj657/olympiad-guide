import argparse
import sys
from datetime import datetime, timezone

from bot.backtest import run_backtest
from bot.config import ExchangeConfig
from bot.data import fetch_ohlcv_range
from bot.exchange import build_exchange, build_public_exchange, futures_symbol
from bot.logger import setup_logger
from bot.risk import RiskParams, is_stop_loss_safe, liquidation_price
from bot.strategies import build_strategy
from bot.trader import run_forever

logger = setup_logger()


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--strategy", choices=["sma", "rsi"], default="sma")
    parser.add_argument("--fast", type=int, default=20, help="SMA: fast period")
    parser.add_argument("--slow", type=int, default=50, help="SMA: slow period")
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-buy", type=float, default=30)
    parser.add_argument("--rsi-sell", type=float, default=70)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--stop-loss-pct", type=float, default=2.0)
    parser.add_argument("--take-profit-pct", type=float, default=4.0)
    parser.add_argument("--fee-pct", type=float, default=0.1)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--market", choices=["spot", "futures"], default="spot",
                         help="spot (no leverage) or futures (leverage, liquidation risk)")
    parser.add_argument("--leverage", type=float, default=1.0,
                         help="Only meaningful with --market futures. 1.0 = no leverage.")


def build_strategy_from_args(args) -> object:
    if args.strategy == "sma":
        return build_strategy("sma", fast_period=args.fast, slow_period=args.slow)
    return build_strategy("rsi", period=args.rsi_period, buy_threshold=args.rsi_buy, sell_threshold=args.rsi_sell)


def build_risk_from_args(args) -> RiskParams:
    leverage = args.leverage if args.market == "futures" else 1.0
    return RiskParams(
        risk_per_trade_pct=args.risk_pct,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        fee_pct=args.fee_pct,
        leverage=leverage,
    )


def warn_if_leverage_unsafe(risk: RiskParams) -> None:
    if risk.leverage <= 1:
        return
    liq = liquidation_price(100.0, risk)
    liq_move_pct = round((100.0 - liq), 2)
    if is_stop_loss_safe(risk):
        logger.info(
            "Leverage %sx: liquidation is ~%s%% away from entry, your %s%% stop-loss fires first (as intended).",
            risk.leverage, liq_move_pct, risk.stop_loss_pct,
        )
    else:
        logger.warning(
            "DANGER: at %sx leverage, liquidation is only ~%s%% away from entry — closer than your "
            "%s%% stop-loss. The exchange will force-close the position (losing the full margin) "
            "BEFORE your stop-loss ever gets a chance to fire. Lower the leverage or widen the gap "
            "between stop-loss and liquidation before trusting this configuration.",
            risk.leverage, liq_move_pct, risk.stop_loss_pct,
        )


def resolve_symbol(symbol: str, market: str) -> str:
    return futures_symbol(symbol) if market == "futures" else symbol


def cmd_backtest(args) -> None:
    exchange = build_public_exchange(market_type=args.market)
    symbol = resolve_symbol(args.symbol, args.market)
    since_ms = int(datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    until_ms = int(datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    risk = build_risk_from_args(args)
    warn_if_leverage_unsafe(risk)

    logger.info("Fetching %s %s candles from %s to %s...", symbol, args.timeframe, args.date_from, args.date_to)
    df = fetch_ohlcv_range(exchange, symbol, args.timeframe, since_ms, until_ms)
    if df.empty:
        logger.error("No candles fetched, check symbol/timeframe/date range.")
        sys.exit(1)

    strategy = build_strategy_from_args(args)
    result = run_backtest(df, strategy, risk, initial_capital=args.capital)

    buy_hold_pct = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100

    print(f"\n=== Backtest: {symbol} {args.timeframe} | strategy={strategy.name} | leverage={risk.leverage}x ===")
    print(f"Period: {df.index[0]} -> {df.index[-1]} ({len(df)} candles)")
    for key, value in result.summary().items():
        print(f"{key}: {value}")
    print(f"buy_and_hold_return_pct: {round(buy_hold_pct, 2)}")


def cmd_paper(args) -> None:
    exchange = build_public_exchange(market_type=args.market)
    symbol = resolve_symbol(args.symbol, args.market)
    strategy = build_strategy_from_args(args)
    risk = build_risk_from_args(args)
    warn_if_leverage_unsafe(risk)
    run_forever(exchange, symbol, args.timeframe, strategy, risk, dry_run=True,
                initial_capital=args.capital, once=args.once)


def cmd_live(args) -> None:
    if not args.i_understand_the_risk:
        print("Live trading uses real funds. Re-run with --i-understand-the-risk to confirm you understand.")
        sys.exit(1)

    config = ExchangeConfig.from_env()
    config.market_type = args.market
    if not config.api_key or not config.api_secret:
        print("Missing API keys. Set BINANCE_API_KEY / BINANCE_API_SECRET in your .env file.")
        sys.exit(1)

    risk = build_risk_from_args(args)
    warn_if_leverage_unsafe(risk)

    if args.market == "futures" and risk.leverage > 1 and not is_stop_loss_safe(risk):
        print(
            f"\nRefusing to start: at {risk.leverage}x leverage your {risk.stop_loss_pct}% stop-loss would "
            "never fire — the exchange liquidates (and takes the full margin) first. Lower --leverage or "
            "raise --stop-loss-pct so the stop-loss is tighter than the liquidation distance, then retry."
        )
        sys.exit(1)

    exchange = build_exchange(config)
    symbol = resolve_symbol(args.symbol, args.market)
    strategy = build_strategy_from_args(args)

    mode = "TESTNET" if config.use_testnet else "REAL MONEY"
    label = f"{mode} ({args.market}, {risk.leverage}x leverage)" if args.market == "futures" else f"{mode} (spot)"
    confirm = input(f"About to trade {symbol} on {label}. Type 'YES' to continue: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        sys.exit(0)

    run_forever(exchange, symbol, args.timeframe, strategy, risk, dry_run=False,
                initial_capital=args.capital, once=args.once)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple crypto trading bot (educational).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_backtest = subparsers.add_parser("backtest", help="Backtest a strategy on historical data")
    add_common_args(p_backtest)
    p_backtest.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    p_backtest.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    p_backtest.set_defaults(func=cmd_backtest)

    p_paper = subparsers.add_parser("paper", help="Paper trade (simulated, no real orders)")
    add_common_args(p_paper)
    p_paper.add_argument("--once", action="store_true", help="Run a single check and exit (useful for cron)")
    p_paper.set_defaults(func=cmd_paper)

    p_live = subparsers.add_parser("live", help="Live trade with real orders (or testnet)")
    add_common_args(p_live)
    p_live.add_argument("--once", action="store_true", help="Run a single check and exit (useful for cron)")
    p_live.add_argument("--i-understand-the-risk", action="store_true",
                         help="Required flag acknowledging live trading risk")
    p_live.set_defaults(func=cmd_live)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
