import os
import sys
import time
import argparse
import threading
from datetime import datetime
from pathlib import Path

# Setup logging to both console and file
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "bot.log"

class LoggerWriter:
    def __init__(self, filepath, stream):
        self.terminal = stream
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        try:
            self.terminal.write(message)
            self.terminal.flush()
        except UnicodeEncodeError:
            self.terminal.write(message.encode("ascii", "replace").decode("ascii"))
            self.terminal.flush()
        try:
            self.log.write(message)
            self.log.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
            self.log.flush()
        except Exception:
            pass

sys.stdout = LoggerWriter(LOG_FILE, sys.stdout)
sys.stderr = LoggerWriter(LOG_FILE, sys.stderr)

from data.data_fetcher import MarketDataFetcher
from data.google_sheets_sync import GoogleSheetsSync
from strategies.nifty_options_strategy import NiftyOptionsStrategy
from risk.risk_manager import RiskManager
from execution.paper_engine import PaperExecutionEngine
from learning.self_learning_engine import SelfLearningEngine
from dashboard.app import app
from config import settings

def start_dashboard_thread():
    """Runs the Flask web dashboard on a background daemon thread."""
    def _run():
        app.run(host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT, debug=False, use_reloader=False)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"[Dashboard] Running on http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")

def is_market_open(now_ist: datetime = None) -> bool:
    """Checks if today is a weekday and current time is within Indian market hours (09:15 to 15:10 IST)."""
    if now_ist is None:
        now_ist = settings.get_now_ist()
    # Monday = 0, Friday = 4, Saturday = 5, Sunday = 6
    if now_ist.weekday() >= 5:
        return False
    time_str = now_ist.strftime("%H:%M")
    return settings.MARKET_OPEN_TIME <= time_str < settings.SQUARE_OFF_TIME

def run_simulation(fetcher, opt_strategy, risk_manager, paper_broker, self_learning_engine=None):
    """
    Simulates recent market session candle-by-candle.
    Allows testing when market is closed at night or on weekends!
    """
    print("\n" + "=" * 65)
    print("  [OFF-MARKET REPLAY SIMULATION: NIFTY 50 OPTIONS]")
    print(f"  Underlying: {settings.INDEX_SYMBOL} | Lot Size: {settings.OPTION_LOT_SIZE}")
    print("=" * 65)

    df = fetcher.get_historical_data(settings.INDEX_SYMBOL, interval=settings.TIMEFRAME, period="5d")
    if df is None or df.empty:
        print("[Simulation] Error: Unable to fetch historical data for simulation.")
        return

    print(f"[Simulation] Loaded {len(df)} candles. Simulating candle feed...")
    min_lookback = max(settings.EMA_SLOW, settings.RSI_PERIOD, settings.ATR_PERIOD) + 2

    # Step through recent candles (last 100 candles)
    start_idx = max(min_lookback, len(df) - 120)
    for i in range(start_idx, len(df)):
        sub_df = df.iloc[:i+1]
        latest_candle = sub_df.iloc[-1]
        ts = sub_df.index[-1]
        
        # Format time for display
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, 'strftime') else str(ts)
        spot_close = float(latest_candle['Close'])
        spot_high = float(latest_candle['High'])
        spot_low = float(latest_candle['Low'])

        # 1. Check existing open positions
        open_keys = list(paper_broker.open_positions.keys())
        for symbol in open_keys:
            pos = paper_broker.open_positions[symbol]
            opt_type = pos.get("option_type", "CE")
            entry_spot = pos.get("entry_spot", spot_close)
            
            # Approximate current option high/low based on spot movement & delta
            if opt_type == "CE":
                spot_diff = spot_close - entry_spot
                curr_opt_price = max(1.0, pos["entry_price"] + spot_diff * settings.OPTION_DELTA)
                curr_opt_high = max(curr_opt_price, pos["entry_price"] + (spot_high - entry_spot) * settings.OPTION_DELTA)
                curr_opt_low = max(1.0, min(curr_opt_price, pos["entry_price"] + (spot_low - entry_spot) * settings.OPTION_DELTA))
            else:  # PE
                spot_diff = entry_spot - spot_close
                curr_opt_price = max(1.0, pos["entry_price"] + spot_diff * settings.OPTION_DELTA)
                curr_opt_high = max(curr_opt_price, pos["entry_price"] + (entry_spot - spot_low) * settings.OPTION_DELTA)
                curr_opt_low = max(1.0, min(curr_opt_price, pos["entry_price"] + (entry_spot - spot_high) * settings.OPTION_DELTA))

            # 1. Active Trailing Stop & Profit Locking evaluated FIRST (tracks candle high)
            updated, new_sl = risk_manager.check_trailing_stop(
                position=pos,
                current_price=curr_opt_price,
                high_price=curr_opt_high,
                low_price=curr_opt_low
            )
            if updated:
                old_sl = pos['stop_loss']
                paper_broker.update_trailing_sl(symbol, new_sl)
                print(f"  [TRAILING SL] {symbol}: SL moved from Rs. {old_sl} to Rs. {new_sl} (Profit Locked!)")

            # 2. Evaluate Exits against Target and (newly updated) Trailing SL
            closed = paper_broker.update_and_check_exits(
                symbol=symbol,
                high_price=curr_opt_high,
                low_price=curr_opt_low,
                close_price=curr_opt_price
            )
            if closed:
                pnl_str = f"Rs. {closed['pnl']:+,.2f} ({closed['pnl_percent']:+,.2f}%)"
                tag = "[PROFIT]" if closed['pnl'] > 0 else ("[BREAKEVEN]" if closed['pnl'] == 0 else "[LOSS]")
                print(f"  {tag} {symbol} Exit @ Rs. {closed['exit_price']} | PnL: {pnl_str} | Reason: {closed['exit_reason']}")
                risk_manager.update_daily_pnl(closed['pnl'])

        # 2. Check for fresh option entry signal
        can_trade, _ = risk_manager.can_open_trade(len(paper_broker.open_positions))
        if can_trade:
            signal_data = opt_strategy.generate_option_signal(sub_df)
            if signal_data is not None:
                contract = signal_data["instrument"]
                if contract not in paper_broker.open_positions:
                    opt_entry = signal_data["price"]
                    opt_sl = signal_data["stop_loss"]
                    opt_tgt = signal_data["target"]
                    risk_per_share = signal_data["option_risk_per_share"]

                    # Calculate quantity in lots
                    risk_amount = risk_manager.risk_per_trade_amount
                    total_shares = max(settings.OPTION_LOT_SIZE, int((risk_amount / risk_per_share) // settings.OPTION_LOT_SIZE) * settings.OPTION_LOT_SIZE)
                    total_shares = min(total_shares, settings.OPTION_LOT_SIZE * settings.MAX_OPTION_LOTS)

                    pos = paper_broker.execute_order(
                        symbol=contract,
                        signal="BUY",
                        price=opt_entry,
                        quantity=total_shares,
                        stop_loss=opt_sl,
                        target=opt_tgt,
                        reason=signal_data["reason"],
                        atr=signal_data["index_atr"]
                    )
                    pos["option_type"] = signal_data["option_type"]
                    pos["entry_spot"] = spot_price = signal_data["underlying_price"]
                    print(f"\n[{ts_str}] [SIGNAL] BUY {total_shares}x {contract} @ Rs. {opt_entry}")
                    print(f"   SL: Rs. {opt_sl} | Target: Rs. {opt_tgt} | Spot: {spot_price}")

        # Sleep briefly for simulation effect
        time.sleep(0.1)

    print("\n[Simulation] Completed replay simulation!")
    paper_broker.print_performance_table()
    
    if paper_broker.sheets_sync:
        paper_broker.sheets_sync.update_summaries_from_history(
            paper_broker.trade_history,
            paper_broker.balance,
            paper_broker.initial_capital
        )

    # Run AI Self-Learning Cycle on simulation results
    if self_learning_engine:
        self_learning_engine.run_eod_cycle(
            paper_broker.trade_history,
            data_fetcher=fetcher,
            sheets_sync=paper_broker.sheets_sync
        )

def main():
    parser = argparse.ArgumentParser(description="Nifty 50 Options Algo Trading Bot")
    parser.add_argument("--simulate", action="store_true", help="Run off-market candle replay simulation")
    args = parser.parse_args()

    print("=" * 70)
    print("   [NIFTY 50 OPTIONS ALGO TRADING BOT - INSTITUTIONAL GRADE]")
    print(f"   Mode: {settings.TRADING_MODE}")
    print(f"   Virtual Capital: Rs. {settings.INITIAL_CAPITAL:,.2f}")
    print(f"   Risk Per Trade: {settings.RISK_PER_TRADE_PERCENT}% | Max Daily Loss: {settings.MAX_DAILY_LOSS_PERCENT}%")
    print(f"   Option Lot Size: {settings.OPTION_LOT_SIZE} | Strike Step: {settings.ATM_STRIKE_STEP}")
    print("=" * 70)

    # 1. Start Web Dashboard Thread
    start_dashboard_thread()

    # 2. Initialize Google Sheets
    print("[GoogleSheets] Initializing Google Sheets connection...")
    sheets_sync = GoogleSheetsSync(
        token_path=settings.GOOGLE_TOKEN_PATH,
        sheet_name=settings.GOOGLE_SHEET_NAME
    )
    if sheets_sync.sheet_url:
        print(f"[GoogleSheets] Live Journal Link: {sheets_sync.sheet_url}")

    # 3. Initialize Core Engines
    fetcher = MarketDataFetcher()
    opt_strategy = NiftyOptionsStrategy()
    risk_manager = RiskManager(initial_capital=settings.INITIAL_CAPITAL)
    paper_broker = PaperExecutionEngine(
        initial_capital=settings.INITIAL_CAPITAL,
        sheets_sync=sheets_sync
    )
    self_learning_engine = SelfLearningEngine()

    # If simulation requested, run it right away
    if args.simulate:
        run_simulation(fetcher, opt_strategy, risk_manager, paper_broker, self_learning_engine)
        if os.getenv("GITHUB_ACTIONS") or os.getenv("CI"):
            print("[Simulation] Completed on GitHub Actions CI. Exiting cleanly.")
            return

        print(f"\n[Info] Dashboard is active at http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")
        print("[Info] Press Ctrl+C to stop dashboard server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    # Pre-checks for Live Trading
    now_ist = settings.get_now_ist()
    time_hm = now_ist.strftime("%H:%M")

    # Weekend check
    if now_ist.weekday() >= 5:
        print(f"\n[Market Closed] Today is {now_ist.strftime('%A')} ({now_ist.strftime('%d-%b-%Y')}).")
        print("[Market Closed] Indian Stock Exchanges (NSE/BSE) are closed on weekends.")
        print("[Market Closed] Bot finished for today.")
        return

    # Post-market check
    if time_hm >= settings.SQUARE_OFF_TIME:
        print(f"\n[Market Closed] Today's session ended at {settings.SQUARE_OFF_TIME} IST (Current time: {time_hm} IST).")
        print("[Market Closed] No new intraday trading allowed after square-off time.")
        print("[Market Closed] For off-market replay simulation, run with '--simulate'. Exiting cleanly.")
        return

    # Pre-market wait (e.g. 09:10 to 09:15 IST)
    if time_hm < settings.MARKET_OPEN_TIME:
        print(f"\n[Bot Engine] Standing by. Market opens at {settings.MARKET_OPEN_TIME} IST (Current: {time_hm} IST).")
        while True:
            now_ist = settings.get_now_ist()
            time_hm = now_ist.strftime("%H:%M")
            if time_hm >= settings.MARKET_OPEN_TIME:
                print(f"[{now_ist.strftime('%H:%M:%S')} IST] Indian Market is now OPEN! Starting algorithmic trading...")
                break
            time.sleep(15)

    print(f"\n[Bot Engine] Active trading loop started at {settings.get_now_ist().strftime('%H:%M:%S')} IST...")
    iteration = 1
    current_day = settings.get_now_ist().date()

    try:
        while True:
            now_ist = settings.get_now_ist()
            time_hm = now_ist.strftime("%H:%M")
            now_str = now_ist.strftime("%H:%M:%S")

            # Check new day reset
            if now_ist.date() != current_day:
                current_day = now_ist.date()
                risk_manager.reset_daily_metrics()
                print(f"\n[{now_str} IST] New trading day started. Resetting daily metrics.")

            # 15:10 IST EOD Square-off check
            if time_hm >= settings.SQUARE_OFF_TIME:
                print(f"\n[{now_str} IST] Intraday Square-off time reached ({settings.SQUARE_OFF_TIME} IST)!")
                # Force square-off all open positions
                open_keys = list(paper_broker.open_positions.keys())
                for symbol in open_keys:
                    pos = paper_broker.open_positions[symbol]
                    opt_type = pos.get("option_type", "CE")
                    entry_spot = pos.get("entry_spot", pos["entry_price"])
                    curr_opt_price = pos["entry_price"]
                    closed = paper_broker.update_and_check_exits(
                        symbol=symbol,
                        high_price=curr_opt_price,
                        low_price=curr_opt_price,
                        close_price=curr_opt_price,
                        force_square_off=True
                    )
                    if closed:
                        pnl_str = f"Rs. {closed['pnl']:+,.2f} ({closed['pnl_percent']:+,.2f}%)"
                        print(f"  [SQUARE-OFF] {symbol} Closed! Exit: Rs. {closed['exit_price']} | PnL: {pnl_str} | Reason: {closed['exit_reason']}")
                        risk_manager.update_daily_pnl(closed['pnl'])

                print(f"[{now_str} IST] Finalizing EOD summaries on Google Sheets...")
                if paper_broker.sheets_sync:
                    paper_broker.sheets_sync.update_summaries_from_history(
                        paper_broker.trade_history,
                        paper_broker.balance,
                        paper_broker.initial_capital
                    )

                # AI Self-Learning & Auto-Optimization Cycle
                self_learning_engine.run_eod_cycle(
                    paper_broker.trade_history,
                    data_fetcher=fetcher,
                    sheets_sync=paper_broker.sheets_sync
                )

                paper_broker.print_performance_table()
                print(f"[{now_str} IST] All trades recorded. Google Sheets synced. Trading day finished successfully!")
                break

            try:
                # Fetch latest Nifty 50 5m candles
                df = fetcher.get_historical_data(settings.INDEX_SYMBOL, interval=settings.TIMEFRAME, period="5d")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    spot_close = float(latest['Close'])
                    spot_high = float(latest['High'])
                    spot_low = float(latest['Low'])

                    # A. Manage active positions
                    open_keys = list(paper_broker.open_positions.keys())
                    for symbol in open_keys:
                        pos = paper_broker.open_positions[symbol]
                        opt_type = pos.get("option_type", "CE")
                        entry_spot = pos.get("entry_spot", spot_close)

                        if opt_type == "CE":
                            spot_diff = spot_close - entry_spot
                            curr_opt_price = max(1.0, pos["entry_price"] + spot_diff * settings.OPTION_DELTA)
                            curr_opt_high = max(curr_opt_price, pos["entry_price"] + (spot_high - entry_spot) * settings.OPTION_DELTA)
                            curr_opt_low = max(1.0, min(curr_opt_price, pos["entry_price"] + (spot_low - entry_spot) * settings.OPTION_DELTA))
                        else:  # PE
                            spot_diff = entry_spot - spot_close
                            curr_opt_price = max(1.0, pos["entry_price"] + spot_diff * settings.OPTION_DELTA)
                            curr_opt_high = max(curr_opt_price, pos["entry_price"] + (entry_spot - spot_low) * settings.OPTION_DELTA)
                            curr_opt_low = max(1.0, min(curr_opt_price, pos["entry_price"] + (entry_spot - spot_high) * settings.OPTION_DELTA))

                        # 1. Active Trailing Stop & Profit Locking evaluated FIRST (tracks candle high)
                        updated, new_sl = risk_manager.check_trailing_stop(
                            position=pos,
                            current_price=curr_opt_price,
                            high_price=curr_opt_high,
                            low_price=curr_opt_low
                        )
                        if updated:
                            old_sl = pos['stop_loss']
                            paper_broker.update_trailing_sl(symbol, new_sl)
                            print(f"[TRAILING SL] {symbol}: Stop-Loss moved from Rs. {old_sl} to Rs. {new_sl} (Profit Locked!)")

                        # 2. Evaluate Exits against Target and (newly updated) Trailing SL
                        closed = paper_broker.update_and_check_exits(
                            symbol=symbol,
                            high_price=curr_opt_high,
                            low_price=curr_opt_low,
                            close_price=curr_opt_price,
                            force_square_off=False
                        )
                        if closed:
                            pnl_str = f"Rs. {closed['pnl']:+,.2f} ({closed['pnl_percent']:+,.2f}%)"
                            tag = "[PROFIT]" if closed['pnl'] > 0 else ("[BREAKEVEN]" if closed['pnl'] == 0 else "[LOSS]")
                            print(f"[{tag}] {symbol} Closed! Exit: Rs. {closed['exit_price']} | PnL: {pnl_str} | Reason: {closed['exit_reason']}")
                            risk_manager.update_daily_pnl(closed['pnl'])

                    # B. Check for new signals if allowed
                    can_trade, reason = risk_manager.can_open_trade(len(paper_broker.open_positions))
                    if can_trade:
                        signal_data = opt_strategy.generate_option_signal(df)
                        if signal_data is not None:
                            contract = signal_data["instrument"]
                            if contract not in paper_broker.open_positions:
                                opt_entry = signal_data["price"]
                                opt_sl = signal_data["stop_loss"]
                                opt_tgt = signal_data["target"]
                                risk_per_share = signal_data["option_risk_per_share"]

                                risk_amount = risk_manager.risk_per_trade_amount
                                total_shares = max(settings.OPTION_LOT_SIZE, int((risk_amount / risk_per_share) // settings.OPTION_LOT_SIZE) * settings.OPTION_LOT_SIZE)
                                total_shares = min(total_shares, settings.OPTION_LOT_SIZE * settings.MAX_OPTION_LOTS)

                                pos = paper_broker.execute_order(
                                    symbol=contract,
                                    signal="BUY",
                                    price=opt_entry,
                                    quantity=total_shares,
                                    stop_loss=opt_sl,
                                    target=opt_tgt,
                                    reason=signal_data["reason"],
                                    atr=signal_data["index_atr"]
                                )
                                risk_manager.increment_trade_count()
                                pos["option_type"] = signal_data["option_type"]
                                pos["entry_spot"] = signal_data["underlying_price"]
                                print(f"\n[{now_str} IST] [SIGNAL] BUY {total_shares}x {contract} @ Rs. {opt_entry}")
                                print(f"   SL: Rs. {opt_sl} | Target: Rs. {opt_tgt} | Underlying Spot: {pos['entry_spot']}")
                else:
                    if iteration % 10 == 1:
                        print(f"[{now_str} IST] Waiting for next market candle update...")

            except Exception as e:
                print(f"[{now_str} IST] Market scan warning: {e}")

            iteration += 1
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n[Bot Engine] Stopping bot...")
        paper_broker.print_performance_table()

if __name__ == "__main__":
    main()
