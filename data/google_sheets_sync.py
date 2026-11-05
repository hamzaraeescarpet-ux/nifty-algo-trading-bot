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
            token_env = os.getenv("GOOGLE_TOKEN_JSON")
            if token_env:
                import json
                token_data = json.loads(token_env)
                creds = Credentials.from_authorized_user_info(token_data)
            elif self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path))
            else:
                print(f"[GoogleSheets] Warning: Neither GOOGLE_TOKEN_JSON env nor token file found at {self.token_path}")
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
        """Ensures clean header row in AI Brain & Learnings."""
        if not self.ai_brain_sheet:
            return
        headers = [
            "Date", "Time (IST)", "Market Regime", "Total Evaluated Trades",
            "Win Rate (%)", "Key Mistake / Pattern Identified",
            "Self-Optimization Action Taken", "Adaptive Settings (ADX, BE_R, Target_R, Max_Trades)"
        ]
        curr_headers = self.ai_brain_sheet.row_values(1)
        if not curr_headers or curr_headers != headers:
            self.ai_brain_sheet.insert_row(headers, index=1)

    def log_ai_learning(self, log_entry: Dict[str, Any]):
        """Logs daily self-learning insights to Google Sheets."""
        if not self.ai_brain_sheet:
            return
        try:
            params = log_entry.get("parameters", {})
            param_str = f"ADX>={params.get('adx_min_threshold')}, BE={params.get('breakeven_r_ratio')}R, Tgt={params.get('risk_reward_ratio')}R, MaxTrades={params.get('max_daily_trades')}"
            row = [
                log_entry.get("date", ""),
                log_entry.get("time", ""),
                log_entry.get("regime", ""),
                int(log_entry.get("total_trades", 0)),
                f"{log_entry.get('win_rate', 0.0):.2f}%",
                log_entry.get("pattern_identified", ""),
                log_entry.get("action_taken", ""),
                param_str
            ]
            self.ai_brain_sheet.append_row(row)
            print(f"[GoogleSheets] Logged AI Self-Learning insights to 'AI Brain & Learnings' tab!")
        except Exception as e:
            print(f"[GoogleSheets] Failed to log AI learning: {e}")

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
