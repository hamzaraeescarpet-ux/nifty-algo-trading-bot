import time
import sys
from datetime import datetime
from data.data_fetcher import MarketDataFetcher
from strategies.confluence_strategy import ConfluenceStrategy
from risk.risk_manager import RiskManager
from execution.paper_engine import PaperExecutionEngine
from config import settings

def is_market_hours() -> bool:
    """Checks if current time is within Indian Market trading hours (9:15 to 15:30 IST)."""
    now = datetime.now().strftime("%H:%M")
    return settings.MARKET_OPEN_TIME <= now <= settings.MARKET_CLOSE_TIME

def run_paper_trading():
    print("=" * 65)
    print("    [INDIAN MARKET ALGO TRADING BOT - PAPER TRADING ENGINE]")
    print(f"    Mode: {settings.TRADING_MODE}")
    print(f"    Starting Virtual Capital: Rs. {settings.INITIAL_CAPITAL:,.2f}")
    print(f"    Risk Per Trade: {settings.RISK_PER_TRADE_PERCENT}% | Max Daily Loss: {settings.MAX_DAILY_LOSS_PERCENT}%")
    print(f"    Target Timeframe: {settings.TIMEFRAME} | Watchlist: {', '.join(settings.WATCHLIST)}")
    print("=" * 65)

    fetcher = MarketDataFetcher()
    strategy = ConfluenceStrategy()
    risk_manager = RiskManager(initial_capital=settings.INITIAL_CAPITAL)
    paper_broker = PaperExecutionEngine(initial_capital=settings.INITIAL_CAPITAL)

    iteration = 1
    current_day = datetime.now().date()

    try:
        while True:
            now = datetime.now()
            now_time = now.strftime("%H:%M:%S")
            time_hm = now.strftime("%H:%M")

            # Check new day reset
            if now.date() != current_day:
                current_day = now.date()
                risk_manager.reset_daily_metrics()
                print(f"\n[SYSTEM {now_time}] New trading day started. Daily metrics reset.")

            # Check EOD square-off (3:15 PM)
            is_eod_squareoff = (time_hm >= settings.SQUARE_OFF_TIME)

            print(f"\n[{now_time}] --- Scan Cycle #{iteration} --- (Open Positions: {len(paper_broker.open_positions)})")

            for symbol in settings.WATCHLIST:
                # Fetch recent candles
                df = fetcher.get_historical_data(symbol, interval=settings.TIMEFRAME, period="5d")
                if df is None or df.empty:
                    continue

                latest_candle = df.iloc[-1]
                high = float(latest_candle['High'])
                low = float(latest_candle['Low'])
                close = float(latest_candle['Close'])

                # 1. Check existing open position for this symbol
                if symbol in paper_broker.open_positions:
                    closed = paper_broker.update_and_check_exits(
                        symbol=symbol,
                        high_price=high,
                        low_price=low,
                        close_price=close,
                        force_square_off=is_eod_squareoff
                    )
                    if closed:
                        pnl_str = f"Rs. {closed['pnl']:+,.2f} ({closed['pnl_percent']:+,.2f}%)"
                        status_tag = "[PROFIT]" if closed['pnl'] > 0 else "[LOSS]"
                        print(f"{status_tag} {symbol} Closed! Reason: {closed['exit_reason']} | PnL: {pnl_str} | Exit: Rs. {closed['exit_price']}")
                        risk_manager.update_daily_pnl(closed['pnl'])
                        continue

                    # If still open, check trailing stop loss
                    pos = paper_broker.open_positions[symbol]
                    updated, new_sl = risk_manager.check_trailing_stop(pos, close)
                    if updated:
                        old_sl = pos['stop_loss']
                        paper_broker.update_trailing_sl(symbol, new_sl)
                        print(f"[TRAILING SL] {symbol}: Stop-Loss moved from Rs. {old_sl} to Rs. {new_sl} to lock profit!")

                # 2. If no open position, scan for new entry
                elif not is_eod_squareoff:
                    can_trade, reason = risk_manager.can_open_trade(len(paper_broker.open_positions))
                    if not can_trade:
                        # Circuit breaker or max positions
                        continue

                    signal_data = strategy.analyze_signal(df)
                    if signal_data is not None:
                        entry_price = signal_data['price']
                        sl = signal_data['stop_loss']
                        target = signal_data['target']
                        atr = signal_data['atr']
                        sig_type = signal_data['signal']

                        qty = risk_manager.calculate_position_size(entry_price, sl)
                        if qty > 0:
                            trade = paper_broker.execute_order(
                                symbol=symbol,
                                signal=sig_type,
                                price=entry_price,
                                quantity=qty,
                                stop_loss=sl,
                                target=target,
                                reason=signal_data['reason'],
                                atr=atr
                            )
                            print(f"\n[NEW SIGNAL] {sig_type} {qty}x {symbol} @ Rs. {entry_price}")
                            print(f"   SL: Rs. {sl} | Target: Rs. {target} | Reason: {signal_data['reason']}")

            # Print brief status
            stats = paper_broker.get_summary_stats()
            print(f"[{now_time}] Virtual Balance: Rs. {stats['balance']:,.2f} | Realized PnL: Rs. {stats['total_pnl']:+,.2f} | Trades: {stats['total_trades']} (Win Rate: {stats['win_rate']}%)")

            iteration += 1
            # Wait 60 seconds before next scan
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n\n[USER STOPPED] Algo Trading Bot shutting down cleanly...")
        paper_broker.print_performance_table()

if __name__ == "__main__":
    run_paper_trading()
