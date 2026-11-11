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

        except Exception as e:
            print(f"[GoogleSheets] Initialization error: {e}")

    def _ensure_trades_header(self):
        """Ensures clean header row in Trade Logs."""
        headers = [
            "Trade ID", "Instrument", "Signal", "Buy Time (Entry)",
            "Sell Time (Exit)", "Buy Price (Rs)", "Sell Price (Rs)", "Qty",
            "Net P&L (Rs)", "Return (%)", "Exit Reason", "Status"
        ]
        curr_headers = self.trades_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
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
        pattern = log_entry.get("pattern_identified", log_entry.get("notes", ""))
        
        if "INITIAL" in regime or "Baseline" in str(pattern):
            pattern_human = "Bot ne institutional rules setup kiye (SuperTrend + VWAP + EMA + RSI Confluence)."
        elif "BEARISH" in regime:
            pattern_human = "Market me achhi girawat dekhi gayi (Nifty continuous selloff me tha). Bot ne high-confidence PE trade me rally capture ki."
        elif "BULLISH" in regime:
            pattern_human = "Market me tezi bani rahi. Bot ne high-confidence signals scan kiye aur false breakout se bachne ke liye patience rakha."
        elif "false breakout" in str(pattern).lower():
            pattern_human = "Market me traps/whipsaws the, isliye confirmation filter ko aur strict kiya gaya."
        else:
            pattern_human = "Market stable aur safe tha. Bot ne koi faltu trade nahi liya aur capital ko protect kiya."

        # 3. Action taken (Human Hinglish)
        action = str(log_entry.get("action_taken", log_entry.get("action", "")))
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
            action_human = "Pichle rules safe aur well-calibrated hain, aaj koi badlaav ki zaroorat nahi padi."
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

    def log_trade(self, trade: Dict[str, Any]):
        """Appends a closed trade to the Trade Logs worksheet."""
        if not self.trades_sheet:
            return

        try:
            buy_time = format_datetime_str(trade.get("entry_time", ""))
            sell_time = format_datetime_str(trade.get("exit_time", ""))
            
            row = [
                trade.get("trade_id", ""),
                trade.get("symbol", ""),
                trade.get("signal", "BUY"),
                buy_time,
                sell_time,
                round(float(trade.get("entry_price", 0.0)), 2),
                round(float(trade.get("exit_price", 0.0)), 2),
                int(trade.get("quantity", 0)),
                round(float(trade.get("pnl", 0.0)), 2),
                f"{trade.get('pnl_percent', 0.0):+,.2f}%",
                trade.get("exit_reason", ""),
                trade.get("status", "CLOSED")
            ]
            self.trades_sheet.append_row(row)
            print(f"[GoogleSheets] Synced trade {trade.get('trade_id')} (Buy: {buy_time} | Sell: {sell_time})")
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
                "Sell Time (Exit)", "Buy Price (Rs)", "Sell Price (Rs)", "Qty",
                "Net P&L (Rs)", "Return (%)", "Exit Reason", "Status"
            ]
            rows = [headers]
            for trade in history:
                buy_time = format_datetime_str(trade.get("entry_time", ""))
                sell_time = format_datetime_str(trade.get("exit_time", ""))
                rows.append([
                    trade.get("trade_id", ""),
                    trade.get("symbol", ""),
                    trade.get("signal", "BUY"),
                    buy_time,
                    sell_time,
                    round(float(trade.get("entry_price", 0.0)), 2),
                    round(float(trade.get("exit_price", 0.0)), 2),
                    int(trade.get("quantity", 0)),
                    round(float(trade.get("pnl", 0.0)), 2),
                    f"{trade.get('pnl_percent', 0.0):+,.2f}%",
                    trade.get("exit_reason", ""),
                    trade.get("status", "CLOSED")
                ])

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

        except Exception as e:
            print(f"[GoogleSheets] Failed to update summaries: {e}")
