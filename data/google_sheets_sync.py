import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import gspread
from google.oauth2.credentials import Credentials

def format_datetime_str(dt_str: str) -> str:
    """Converts any datetime format into 'DD-Mon-YYYY HH:MM:SS' (e.g. '12-Oct-2026 09:35:10')."""
    if not dt_str:
        return ""
    try:
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%b-%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f"
        ):
            try:
                dt = datetime.strptime(str(dt_str).strip(), fmt)
                return dt.strftime("%d-%b-%Y %H:%M:%S")
            except ValueError:
                pass
    except Exception:
        pass
    return str(dt_str)

def extract_date_and_month(dt_str: str):
    """Returns (DD-Mon-YYYY, Mon-YYYY) for grouping."""
    formatted = format_datetime_str(dt_str)
    try:
        dt = datetime.strptime(formatted, "%d-%b-%Y %H:%M:%S")
        return dt.strftime("%d-%b-%Y"), dt.strftime("%b-%Y")
    except Exception:
        parts = formatted.split(" ")
        date_p = parts[0] if parts else formatted
        return date_p, date_p

class GoogleSheetsSync:
    """
    Syncs trades, daily PnL, and monthly statistics directly to Google Sheets.
    - Trade Logs: Explicit Buy Time and Sell Time columns.
    - Daily Summary: Automatic daily totals and lifetime summary.
    - Monthly Summary: Automatic monthly performance totals.
    """
    def __init__(
        self,
        token_path: str = r"C:\Users\hamza\Downloads\python development\amro store\google_token.json",
        sheet_name: str = "Nifty50_Algo_Trading_Journal"
    ):
        self.token_path = Path(token_path)
        self.sheet_name = sheet_name
        self.client = None
        self.spreadsheet = None
        self.trades_sheet = None
        self.daily_sheet = None
        self.monthly_sheet = None
        self.ai_brain_sheet = None
        self.calendar_sheet = None
        self.sheet_url = ""
        self._initialize()

    def _initialize(self):
        """Authenticates and sets up required worksheets with clean headers."""
        try:
            from google.oauth2 import service_account
            token_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_TOKEN_JSON")
            sa_file = Path("service_account.json")
            
            creds = None
            if token_env:
                import json
                data = json.loads(token_env)
                if data.get("type") == "service_account":
                    creds = service_account.Credentials.from_service_account_info(
                        data,
                        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                    )
                else:
                    creds = Credentials.from_authorized_user_info(data)
            elif sa_file.exists():
                creds = service_account.Credentials.from_service_account_file(
                    str(sa_file),
                    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                )
            elif self.token_path.exists():
                import json
                with open(self.token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("type") == "service_account":
                    creds = service_account.Credentials.from_service_account_info(
                        data,
                        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                    )
                else:
                    creds = Credentials.from_authorized_user_info(data)
            else:
                print(f"[GoogleSheets] Warning: No valid Google credentials found.")
                return

            self.client = gspread.authorize(creds)

            # Check if spreadsheet already exists, else create it
            try:
                self.spreadsheet = self.client.open(self.sheet_name)
            except gspread.SpreadsheetNotFound:
                print(f"[GoogleSheets] Creating new spreadsheet: '{self.sheet_name}'...")
                self.spreadsheet = self.client.create(self.sheet_name)

            self.sheet_url = self.spreadsheet.url
            print(f"[GoogleSheets] Connected: {self.sheet_url}")

            # 1. Setup 'Trade Logs' tab
            try:
                self.trades_sheet = self.spreadsheet.worksheet("Trade Logs")
            except gspread.WorksheetNotFound:
                self.trades_sheet = self.spreadsheet.add_worksheet(title="Trade Logs", rows=1000, cols=15)
            self._ensure_trades_header()

            # 2. Setup 'Daily Summary' tab
            try:
                self.daily_sheet = self.spreadsheet.worksheet("Daily Summary")
            except gspread.WorksheetNotFound:
                self.daily_sheet = self.spreadsheet.add_worksheet(title="Daily Summary", rows=500, cols=10)
            self._ensure_daily_header()

            # 3. Setup 'Monthly Summary' tab
            try:
                self.monthly_sheet = self.spreadsheet.worksheet("Monthly Summary")
            except gspread.WorksheetNotFound:
                self.monthly_sheet = self.spreadsheet.add_worksheet(title="Monthly Summary", rows=100, cols=10)
            self._ensure_monthly_header()

            # 4. Setup 'AI Brain & Learnings' tab
            try:
                self.ai_brain_sheet = self.spreadsheet.worksheet("AI Brain & Learnings")
            except gspread.WorksheetNotFound:
                self.ai_brain_sheet = self.spreadsheet.add_worksheet(title="AI Brain & Learnings", rows=500, cols=10)
            self._ensure_ai_brain_header()

            # 5. Setup 'Trading Calendar' tab
            try:
                self.calendar_sheet = self.spreadsheet.worksheet("Trading Calendar")
            except gspread.WorksheetNotFound:
                self.calendar_sheet = self.spreadsheet.add_worksheet(title="Trading Calendar", rows=100, cols=10)

        except Exception as e:
            print(f"[GoogleSheets] Initialization error: {e}")

    def _ensure_trades_header(self):
        """Ensures clean header row in Trade Logs with detailed price extremes & entry reason."""
        headers = [
            "Trade ID", "Instrument", "Signal", "Buy Time (Entry)",
            "Sell Time (Exit)", "Buy Price (Rs)", "Upar Kitna Gaya - High (Rs)",
            "Neeche Kitna Gaya - Low (Rs)", "Max Gain Potential", "Sell Price (Rs)", "Qty",
            "Net P&L (Rs)", "Return (%)", "Trade Lene Ka Valid Reason", "Exit Reason", "Status"
        ]
        curr_headers = self.trades_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
            self.trades_sheet.clear()
            self.trades_sheet.insert_row(headers, index=1)

    def _ensure_daily_header(self):
        """Ensures clean header row in Daily Summary."""
        headers = [
            "Date", "Total Trades", "Wins", "Losses",
            "Win Rate (%)", "Daily Net P&L (Rs)", "Closing Capital (Rs)"
        ]
        curr_headers = self.daily_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
            self.daily_sheet.insert_row(headers, index=1)

    def _ensure_monthly_header(self):
        """Ensures clean header row in Monthly Summary."""
        headers = [
            "Month", "Total Trades", "Wins", "Losses",
            "Win Rate (%)", "Monthly Net P&L (Rs)", "Ending Capital (Rs)"
        ]
        curr_headers = self.monthly_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
            self.monthly_sheet.insert_row(headers, index=1)

    def _ensure_ai_brain_header(self):
        """Ensures clean, human-friendly header row in AI Brain & Learnings."""
        if not self.ai_brain_sheet:
            return
        headers = [
            "Date & Time",
            "Market Ka Haal (Condition)",
            "Trades Performance",
            "Market Me Kya Dekha / Seekha (Pattern & Analysis)",
            "Bot Ne Apne Rules Kaise Sudhare (Self-Optimization)",
            "Naye Trading Rules (Simple Settings)"
        ]
        curr_headers = self.ai_brain_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
            self.ai_brain_sheet.insert_row(headers, index=1)

    def _format_human_learning_row(self, log_entry: Dict[str, Any]) -> List[str]:
        """Converts technical AI decision metrics into simple, clear human-readable language."""
        regime = str(log_entry.get("regime", "")).upper()
        
        # 1. Market condition in easy terms
        if "BEARISH" in regime:
            regime_human = "📉 Badi Girawat (Down Trend)"
        elif "BULLISH" in regime:
            regime_human = "📈 Badi Tezi (Up Trend)"
        elif "CHOPPY" in regime or "SIDEWAYS" in regime:
            regime_human = "↔️ Sideways (Rangebound - No Big Move)"
        elif "VOLATILITY" in regime:
            regime_human = "⚡ High Volatility (Jhatke Wala Market)"
        else:
            regime_human = "⚙️ Pehla Setup (Initial Calibration)"

        # 2. Pattern Identified (Human Hinglish)
        pattern = str(log_entry.get("pattern_identified", log_entry.get("notes", "")))
        action = str(log_entry.get("action_taken", log_entry.get("action", "")))
        
        if any(k in pattern for k in ["Session Post-Mortem", "Zero-Noise", "Breakeven Whipsaw", "Strong Trend", "False Breakout"]):
            pattern_human = pattern
        elif "INITIAL" in regime or "Baseline" in pattern:
            pattern_human = "Bot ne institutional rules setup kiye (SuperTrend + VWAP + EMA + RSI Confluence)."
        elif "BEARISH" in regime:
            pattern_human = "Market me achhi girawat dekhi gayi (Nifty continuous selloff me tha). Bot ne high-confidence PE trade me rally capture ki."
        elif "BULLISH" in regime:
            pattern_human = "Market me tezi bani rahi. Bot ne high-confidence signals scan kiye aur false breakout se bachne ke liye patience rakha."
        elif "false breakout" in pattern.lower():
            pattern_human = "Market me traps/whipsaws the, isliye confirmation filter ko aur strict kiya gaya."
        else:
            pattern_human = pattern if pattern else "Market stable aur safe tha. Bot ne koi faltu trade nahi liya aur capital ko protect kiya."

        # 3. Action taken (Human Hinglish)
        if any(k in action for k in ["Anti-Whipsaw", "saans lene", "breathing room", "Multi-Stage", "Profit Locking", "Cooldown"]):
            action_human = action
        else:
            actions_human = []
            if "Expanded Target" in action or "1:2" in action:
                actions_human.append("Target badhakar 1:2 kiya (Trend me bada profit capture karne ke liye)")
            if "Capped Max Daily Trades" in action or "2" in action:
                actions_human.append("Din me Maximum 2 trades limit set ki (Overtrading aur faltu loss rokne ke liye)")
            if "Raised ADX" in action:
                actions_human.append("Trend confirmation filter badhaya (Taaki trap na ho)")
            if "Breakeven trigger" in action:
                actions_human.append("Stop-loss ko jaldi safe karne ka niyam lagaya")
            
            if not actions_human:
                action_human = action if action else "Pichle rules safe aur well-calibrated hain, aaj koi badlaav ki zaroorat nahi padi."
            else:
                action_human = " | ".join(actions_human)

        # 4. Settings summary
        params = log_entry.get("parameters", {})
        adx_v = params.get("adx_min_threshold", 20.0)
        tgt_v = params.get("risk_reward_ratio", 2.0)
        max_t = params.get("max_daily_trades", 2)
        
        if adx_v and tgt_v and max_t:
            settings_human = f"Trend Power: {adx_v}+ | Target: {tgt_v}x Profit | Max Trades: {max_t}/Day"
        else:
            settings_human = "Default Rules (Trend Filter: 20+, 1:2 R:R, Max 2 Trades)"

        # Performance
        total_t = int(log_entry.get("total_trades", 0))
        win_r = float(log_entry.get("win_rate", 0.0))
        perf_human = f"{total_t} Total Trades | Win Rate: {win_r:.1f}%"

        date_val = log_entry.get("date", "")
        time_val = log_entry.get("time", "15:10:00")
        dt_display = f"{date_val} {time_val}"

        return [
            dt_display,
            regime_human,
            perf_human,
            pattern_human,
            action_human,
            settings_human
        ]

    def log_ai_learning(self, log_entry: Dict[str, Any]):
        """Logs daily self-learning insights to Google Sheets in human-readable language."""
        if not self.ai_brain_sheet:
            return
        try:
            row = self._format_human_learning_row(log_entry)
            self.ai_brain_sheet.append_row(row)
            print(f"[GoogleSheets] Logged AI Self-Learning insights to 'AI Brain & Learnings' tab!")
        except Exception as e:
            print(f"[GoogleSheets] Failed to log AI learning: {e}")

    def sync_all_ai_learnings(self, adaptive_file: Optional[Path] = None):
        """Syncs all historic learning entries from adaptive_weights.json to 'AI Brain & Learnings'."""
        if not self.ai_brain_sheet:
            return
        try:
            import json
            af = Path(adaptive_file) if adaptive_file else Path("config/adaptive_weights.json")
            if not af.exists():
                return
            with open(af, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            logs = data.get("learning_logs", [])
            if not logs:
                return

            # Clear existing data and rewrite clean headers
            self.ai_brain_sheet.clear()
            self._ensure_ai_brain_header()

            rows = [self._format_human_learning_row(entry) for entry in logs]
            if rows:
                self.ai_brain_sheet.append_rows(rows)
                print(f"[GoogleSheets] Successfully synced {len(rows)} AI learning logs to 'AI Brain & Learnings' tab!")
        except Exception as e:
            print(f"[GoogleSheets] Failed to sync AI learnings history: {e}")

    def _format_trade_row(self, trade: Dict[str, Any]) -> List[Any]:
        """Builds a comprehensive, transparent trade log row."""
        buy_time = format_datetime_str(trade.get("entry_time", ""))
        sell_time = format_datetime_str(trade.get("exit_time", ""))
        entry_p = round(float(trade.get("entry_price", 0.0)), 2)
        exit_p = round(float(trade.get("exit_price", 0.0)), 2)
        high_p = round(float(trade.get("highest_price", entry_p)), 2)
        low_p = round(float(trade.get("lowest_price", entry_p)), 2)
        
        # Calculate max potential move
        direction = trade.get("signal", "BUY")
        if direction == "BUY":
            max_gain_pts = max(0.0, round(high_p - entry_p, 2))
        else:
            max_gain_pts = max(0.0, round(entry_p - low_p, 2))
            
        gain_pct = round((max_gain_pts / entry_p) * 100, 1) if entry_p > 0 else 0.0
        max_gain_str = f"+{max_gain_pts:.2f} pts (+{gain_pct:.1f}%)" if max_gain_pts > 0 else "+0.00 pts"

        reason = str(trade.get("reason", "Confluence Signal"))
        # Shorten and clarify reason for mobile readability
        if "Bearish Confluence" in reason:
            reason_clean = "Nifty Downfall Confluence (ST Red + Below VWAP + EMA 20<50 + ADX Confirm)"
        elif "Bullish Confluence" in reason:
            reason_clean = "Nifty Rally Confluence (ST Green + Above VWAP + EMA 20>50 + ADX Confirm)"
        else:
            reason_clean = reason

        pnl = round(float(trade.get("pnl", 0.0)), 2)
        pnl_pct_str = f"{trade.get('pnl_percent', 0.0):+,.2f}%"

        exit_r = str(trade.get("exit_reason", ""))
        if "TRAILING SL" in exit_r and pnl == 0:
            exit_r = "TRAILING SL HIT (Cost-to-Cost Protected, Rs 0 Loss)"
        elif "TRAILING SL" in exit_r and pnl > 0:
            exit_r = f"TRAILING SL HIT (Profit Locked In: Rs {pnl:+,.2f})"

        return [
            trade.get("trade_id", ""),
            trade.get("symbol", ""),
            trade.get("signal", "BUY"),
            buy_time,
            sell_time,
            entry_p,
            high_p,
            low_p,
            max_gain_str,
            exit_p,
            int(trade.get("quantity", 0)),
            pnl,
            pnl_pct_str,
            reason_clean,
            exit_r,
            trade.get("status", "CLOSED")
        ]

    def log_trade(self, trade: Dict[str, Any]):
        """Appends a closed trade to the Trade Logs worksheet."""
        if not self.trades_sheet:
            return

        try:
            row = self._format_trade_row(trade)
            self.trades_sheet.append_row(row)
            print(f"[GoogleSheets] Synced trade {trade.get('trade_id')} (High: {row[6]} | Low: {row[7]} | Max Gain: {row[8]})")
        except Exception as e:
            print(f"[GoogleSheets] Failed to log trade: {e}")

    def sync_all_history_to_sheets(self, history: List[Dict[str, Any]], current_balance: float, initial_capital: float = 100000.0):
        """Rewrites all worksheets with standardized date formatting."""
        if not self.trades_sheet:
            return

        try:
            self._ensure_trades_header()
            headers = [
                "Trade ID", "Instrument", "Signal", "Buy Time (Entry)",
                "Sell Time (Exit)", "Buy Price (Rs)", "Upar Kitna Gaya - High (Rs)",
                "Neeche Kitna Gaya - Low (Rs)", "Max Gain Potential", "Sell Price (Rs)", "Qty",
                "Net P&L (Rs)", "Return (%)", "Trade Lene Ka Valid Reason", "Exit Reason", "Status"
            ]
            rows = [headers]
            for trade in history:
                rows.append(self._format_trade_row(trade))

            self.trades_sheet.clear()
            self.trades_sheet.update(range_name='A1', values=rows)
            print(f"[GoogleSheets] Synced all {len(history)} trades to Trade Logs!")
            self.update_summaries_from_history(history, current_balance, initial_capital)
        except Exception as e:
            print(f"[GoogleSheets] Failed to sync full history: {e}")

    def update_summaries_from_history(self, history: List[Dict[str, Any]], current_balance: float, initial_capital: float = 100000.0):
        """
        Groups all trades by Day and Month, calculates metrics,
        and rewrites clean Daily and Monthly summary tables with totals.
        """
        if not history or not self.daily_sheet or not self.monthly_sheet:
            return

        try:
            daily_groups: Dict[str, List[Dict[str, Any]]] = {}
            monthly_groups: Dict[str, List[Dict[str, Any]]] = {}

            for t in history:
                # Parse date
                raw_time = t.get("exit_time") or t.get("entry_time") or ""
                date_part, month_part = extract_date_and_month(raw_time)

                daily_groups.setdefault(date_part, []).append(t)
                monthly_groups.setdefault(month_part, []).append(t)

            # --- Update Daily Summary Sheet ---
            daily_rows = [[
                "Date", "Total Trades", "Wins", "Losses",
                "Win Rate (%)", "Daily Net P&L (Rs)", "Closing Capital (Rs)"
            ]]
            
            running_cap = initial_capital
            total_wins_all = 0
            total_losses_all = 0
            total_pnl_all = 0.0

            for d in sorted(daily_groups.keys()):
                trades = daily_groups[d]
                wins = sum(1 for x in trades if x.get("pnl", 0) > 0)
                losses = sum(1 for x in trades if x.get("pnl", 0) <= 0)
                day_pnl = sum(x.get("pnl", 0) for x in trades)
                win_rate = (wins / len(trades)) * 100 if trades else 0.0
                running_cap += day_pnl

                total_wins_all += wins
                total_losses_all += losses
                total_pnl_all += day_pnl

                daily_rows.append([
                    d, len(trades), wins, losses,
                    f"{win_rate:.2f}%", round(day_pnl, 2), round(running_cap, 2)
                ])

            # Lifetime Total row for Daily
            total_trades_count = len(history)
            overall_win_rate = (total_wins_all / total_trades_count * 100) if total_trades_count > 0 else 0.0
            daily_rows.append([
                "TOTAL SUMMARY", total_trades_count, total_wins_all, total_losses_all,
                f"{overall_win_rate:.2f}%", round(total_pnl_all, 2), round(current_balance, 2)
            ])

            self.daily_sheet.clear()
            self.daily_sheet.update(range_name='A1', values=daily_rows)
            print("[GoogleSheets] Daily Summary updated with full totals!")

            # --- Update Monthly Summary Sheet ---
            monthly_rows = [[
                "Month", "Total Trades", "Wins", "Losses",
                "Win Rate (%)", "Monthly Net P&L (Rs)", "Ending Capital (Rs)"
            ]]

            m_running_cap = initial_capital
            for m in sorted(monthly_groups.keys()):
                trades = monthly_groups[m]
                wins = sum(1 for x in trades if x.get("pnl", 0) > 0)
                losses = sum(1 for x in trades if x.get("pnl", 0) <= 0)
                m_pnl = sum(x.get("pnl", 0) for x in trades)
                win_rate = (wins / len(trades)) * 100 if trades else 0.0
                m_running_cap += m_pnl

                monthly_rows.append([
                    m, len(trades), wins, losses,
                    f"{win_rate:.2f}%", round(m_pnl, 2), round(m_running_cap, 2)
                ])

            # Lifetime Total row for Monthly
            monthly_rows.append([
                "TOTAL SUMMARY", total_trades_count, total_wins_all, total_losses_all,
                f"{overall_win_rate:.2f}%", round(total_pnl_all, 2), round(current_balance, 2)
            ])

            self.monthly_sheet.clear()
            self.monthly_sheet.update(range_name='A1', values=monthly_rows)
            print("[GoogleSheets] Monthly Summary updated with full totals!")

            # --- Sync Trading Calendar Heatmap ---
            self.sync_trading_calendar(history)

        except Exception as e:
            print(f"[GoogleSheets] Failed to update summaries: {e}")

    def sync_trading_calendar(self, history: Optional[List[Dict[str, Any]]] = None):
        """
        Builds and syncs an interactive, trader-favorite monthly PnL calendar:
        - Columns: SUN, MON, TUE, WED, THU, FRI, SAT, TOTAL
        - Cell data: Day of month, trades count, and realized net PnL (Rs)
        - Colors: Green for profit days, Red for loss days, Neutral (Cyan/Grey) for 0 trade/breakeven days.
        """
        if not self.calendar_sheet:
            return

        import calendar
        from datetime import datetime

        try:
            # Load trades if not passed
            if history is None:
                journal_p = Path("logs/paper_trades_journal.json")
                if journal_p.exists():
                    import json
                    with open(journal_p, "r", encoding="utf-8") as f:
                        j_data = json.load(f)
                    history = j_data.get("history", [])
                else:
                    history = []

            # Aggregate daily pnl
            daily_stats = {}
            for t in history:
                raw_time = t.get("entry_time", "") or t.get("exit_time", "")
                if not raw_time:
                    continue
                try:
                    dt = datetime.strptime(raw_time.split(" ")[0], "%d-%b-%Y")
                    date_key = dt.strftime("%Y-%m-%d")
                except Exception:
                    continue

                if date_key not in daily_stats:
                    daily_stats[date_key] = {"trades": 0, "pnl": 0.0}

                daily_stats[date_key]["trades"] += 1
                daily_stats[date_key]["pnl"] += float(t.get("pnl", 0.0))

            def c(r, g, b):
                return {"red": r / 255.0, "green": g / 255.0, "blue": b / 255.0}

            C_PROFIT_BG = c(212, 237, 218)       # Soft Green
            C_PROFIT_TXT = c(21, 87, 36)
            C_LOSS_BG = c(248, 215, 218)         # Soft Red
            C_LOSS_TXT = c(114, 28, 36)
            C_BREAKEVEN_BG = c(209, 236, 241)    # Soft Cyan/Blue
            C_BREAKEVEN_TXT = c(12, 84, 96)
            C_NOTRADE_BG = c(248, 249, 250)      # Pale Neutral
            C_NOTRADE_TXT = c(108, 117, 125)
            C_HEADER_BG = c(200, 230, 201)       # Soft Mint Header
            C_HEADER_TXT = c(27, 94, 32)
            C_TOTAL_BG = c(255, 243, 205)        # Champagne Total
            C_TOTAL_TXT = c(133, 100, 4)
            C_TITLE_BG = c(44, 62, 80)           # Navy Title Banner
            C_TITLE_TXT = c(255, 255, 255)

            now = datetime.now()
            months_to_render = [(now.year, now.month)]
            seen_months = sorted(list({k[:7] for k in daily_stats.keys()}), reverse=True)
            for ym in seen_months:
                try:
                    y, m = map(int, ym.split("-"))
                    if (y, m) not in months_to_render:
                        months_to_render.append((y, m))
                except Exception:
                    pass

            all_rows = []
            batch_requests = []
            curr_row = 1
            cal_id = self.calendar_sheet.id

            for year, month in months_to_render:
                m_name = calendar.month_name[month].upper()
                m_trades = sum(s["trades"] for d, s in daily_stats.items() if d.startswith(f"{year:04d}-{month:02d}"))
                m_pnl = sum(s["pnl"] for d, s in daily_stats.items() if d.startswith(f"{year:04d}-{month:02d}"))
                m_pnl_str = f"+Rs. {m_pnl:,.2f}" if m_pnl > 0 else (f"-Rs. {abs(m_pnl):,.2f}" if m_pnl < 0 else "Rs. 0.00")

                banner_text = f"📅 {m_name} {year} - TRADING PERFORMANCE CALENDAR | Total P&L: {m_pnl_str} | Total Trades: {m_trades}"
                all_rows.append([banner_text, "", "", "", "", "", "", ""])

                batch_requests.append({
                    "mergeCells": {
                        "range": {
                            "sheetId": cal_id,
                            "startRowIndex": curr_row - 1,
                            "endRowIndex": curr_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": 8
                        },
                        "mergeType": "MERGE_ALL"
                    }
                })
                batch_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": cal_id,
                            "startRowIndex": curr_row - 1,
                            "endRowIndex": curr_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": 8
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": C_TITLE_BG,
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {"foregroundColor": C_TITLE_TXT, "bold": True, "fontSize": 12}
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                    }
                })
                curr_row += 1

                # Weekday Headers
                all_rows.append(["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT", "TOTAL"])
                batch_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": cal_id,
                            "startRowIndex": curr_row - 1,
                            "endRowIndex": curr_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": 8
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": C_HEADER_BG,
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {"foregroundColor": C_HEADER_TXT, "bold": True, "fontSize": 11}
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                    }
                })
                curr_row += 1

                # Grid
                c_obj = calendar.Calendar(firstweekday=6)
                weeks = c_obj.monthdayscalendar(year, month)
                grid_start = curr_row

                for w_idx, week in enumerate(weeks):
                    r_vals = []
                    w_trades = 0
                    w_pnl = 0.0

                    for col_idx, day in enumerate(week):
                        if day == 0:
                            r_vals.append("")
                            cell_bg = c(255, 255, 255)
                            cell_txt = c(128, 128, 128)
                            is_bold = False
                        else:
                            date_str = f"{year:04d}-{month:02d}-{day:02d}"
                            stats = daily_stats.get(date_str, {"trades": 0, "pnl": 0.0})
                            t_count = stats["trades"]
                            pnl = stats["pnl"]
                            w_trades += t_count
                            w_pnl += pnl

                            if pnl > 0:
                                p_str = f"+Rs. {pnl:,.2f}"
                                cell_bg = C_PROFIT_BG
                                cell_txt = C_PROFIT_TXT
                                is_bold = True
                            elif pnl < 0:
                                p_str = f"-Rs. {abs(pnl):,.2f}"
                                cell_bg = C_LOSS_BG
                                cell_txt = C_LOSS_TXT
                                is_bold = True
                            elif t_count > 0:
                                p_str = "Rs. 0.00"
                                cell_bg = C_BREAKEVEN_BG
                                cell_txt = C_BREAKEVEN_TXT
                                is_bold = True
                            else:
                                p_str = "Rs. 0.00"
                                cell_bg = C_NOTRADE_BG
                                cell_txt = C_NOTRADE_TXT
                                is_bold = False

                            r_vals.append(f"{day}\n{t_count} trades\n{p_str}")

                        batch_requests.append({
                            "repeatCell": {
                                "range": {
                                    "sheetId": cal_id,
                                    "startRowIndex": curr_row - 1,
                                    "endRowIndex": curr_row,
                                    "startColumnIndex": col_idx,
                                    "endColumnIndex": col_idx + 1
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "backgroundColor": cell_bg,
                                        "horizontalAlignment": "CENTER",
                                        "verticalAlignment": "MIDDLE",
                                        "wrapStrategy": "WRAP",
                                        "textFormat": {"foregroundColor": cell_txt, "bold": is_bold, "fontSize": 10}
                                    }
                                },
                                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"
                            }
                        })

                    # Week Total column
                    w_pnl_str = f"+Rs. {w_pnl:,.2f}" if w_pnl > 0 else (f"-Rs. {abs(w_pnl):,.2f}" if w_pnl < 0 else "Rs. 0.00")
                    r_vals.append(f"Week {w_idx + 1}\n{w_trades} trades\n{w_pnl_str}")

                    batch_requests.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": cal_id,
                                "startRowIndex": curr_row - 1,
                                "endRowIndex": curr_row,
                                "startColumnIndex": 7,
                                "endColumnIndex": 8
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": C_TOTAL_BG,
                                    "horizontalAlignment": "CENTER",
                                    "verticalAlignment": "MIDDLE",
                                    "wrapStrategy": "WRAP",
                                    "textFormat": {"foregroundColor": C_TOTAL_TXT, "bold": True, "fontSize": 10}
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"
                        }
                    })

                    all_rows.append(r_vals)
                    curr_row += 1

                # Grid borders
                batch_requests.append({
                    "updateBorders": {
                        "range": {
                            "sheetId": cal_id,
                            "startRowIndex": grid_start - 1,
                            "endRowIndex": curr_row - 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 8
                        },
                        "top": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                        "bottom": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                        "left": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                        "right": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                        "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                        "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}}
                    }
                })

                all_rows.append(["", "", "", "", "", "", "", ""])
                all_rows.append(["", "", "", "", "", "", "", ""])
                curr_row += 2

            for col_i in range(8):
                batch_requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": cal_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_i,
                            "endIndex": col_i + 1
                        },
                        "properties": {"pixelSize": 125},
                        "fields": "pixelSize"
                    }
                })

            self.calendar_sheet.clear()
            self.calendar_sheet.update(range_name='A1', values=all_rows)
            if batch_requests:
                self.spreadsheet.batch_update({"requests": batch_requests})
            print(f"[GoogleSheets] 'Trading Calendar' successfully updated with colourful PnL heatmap!")

        except Exception as e:
            print(f"[GoogleSheets] Failed to sync trading calendar: {e}")
