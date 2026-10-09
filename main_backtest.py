import sys
import argparse
from data.data_fetcher import MarketDataFetcher
from backtest.backtester import Backtester
from config import settings

def run_backtest_for_symbol(symbol: str, days: str = "30d", interval: str = "5m"):
    print(f"\n[INFO] Fetching {interval} data for {symbol} (Period: {days})...")
    fetcher = MarketDataFetcher()
    df = fetcher.get_historical_data(symbol, interval=interval, period=days)

    if df is None or df.empty:
        print(f"[ERROR] Could not fetch data for {symbol}. Check internet or ticker symbol.")
        return

    print(f"[INFO] Loaded {len(df)} candles. Starting Strategy Backtest simulation...")
    backtester = Backtester(initial_capital=settings.INITIAL_CAPITAL)
    report = backtester.run(df, symbol)
    backtester.print_report(report)

    if backtester.trades:
        print(f"\nLast 5 Trades executed in Backtest for {symbol}:")
        import pandas as pd
        trades_df = pd.DataFrame(backtester.trades)[['signal', 'entry_time', 'entry_price', 'exit_time', 'exit_price', 'pnl', 'exit_reason']]
        print(trades_df.tail(5).to_string(index=False))

def main():
    parser = argparse.ArgumentParser(description="Intraday Algo Trading Strategy Backtester")
    parser.add_argument("--symbol", type=str, default="RELIANCE.NS", help="NSE Ticker symbol (e.g. RELIANCE.NS, TCS.NS, INFY.NS)")
    parser.add_argument("--days", type=str, default="30d", help="Backtest period (e.g. 15d, 30d, 60d)")
    parser.add_argument("--interval", type=str, default="5m", help="Candle timeframe (e.g. 5m, 15m)")
    parser.add_argument("--all", action="store_true", help="Run backtest on all watchlist stocks")
    args = parser.parse_args()

    if args.all:
        print(f"[INFO] Running backtest across all watchlist stocks: {settings.WATCHLIST}")
        for sym in settings.WATCHLIST:
            run_backtest_for_symbol(sym, days=args.days, interval=args.interval)
    else:
        run_backtest_for_symbol(args.symbol, days=args.days, interval=args.interval)

if __name__ == "__main__":
    main()
