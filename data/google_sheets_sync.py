import os
from pathlib import Path
from typing import Dict, Any, Optional
import gspread
from google.oauth2.credentials import Credentials

class GoogleSheetsSync:
    """
    Syncs trades, daily PnL, and monthly statistics directly to Google Sheets.
    Uses existing credentials from amro store.
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
                # Share with user's drive if needed
                
            self.sheet_url = self.spreadsheet.url
            print(f"[GoogleSheets] Connected: {self.sheet_url}")

            # 1. Setup 'Trade Logs' tab
            try:
                self.trades_sheet = self.spreadsheet.worksheet("Trade Logs")
            except gspread.WorksheetNotFound:
                self.trades_sheet = self.spreadsheet.add_worksheet(title="Trade Logs", rows=1000, cols=15)
                # Header row
                self.trades_sheet.append_row([
                    "Trade ID", "Date & Time", "Instrument", "Signal",
                    "Entry Price", "Exit Price", "Qty", "PnL (Rs)",
                    "PnL (%)", "Exit Reason", "Status"
                ])

            # 2. Setup 'Daily Summary' tab
            try:
                self.daily_sheet = self.spreadsheet.worksheet("Daily Summary")
            except gspread.WorksheetNotFound:
                self.daily_sheet = self.spreadsheet.add_worksheet(title="Daily Summary", rows=500, cols=10)
                self.daily_sheet.append_row([
                    "Date", "Total Trades", "Wins", "Losses",
                    "Win Rate (%)", "Daily Net PnL (Rs)", "Closing Balance (Rs)"
                ])

            # 3. Setup 'Monthly Summary' tab
            try:
                self.monthly_sheet = self.spreadsheet.worksheet("Monthly Summary")
            except gspread.WorksheetNotFound:
                self.monthly_sheet = self.spreadsheet.add_worksheet(title="Monthly Summary", rows=100, cols=8)
                self.monthly_sheet.append_row([
                    "Month", "Total Trades", "Net PnL (Rs)", "Return (%)", "Ending Capital (Rs)"
                ])

        except Exception as e:
            print(f"[GoogleSheets] Initialization error: {e}")

    def log_trade(self, trade: Dict[str, Any]):
        """Appends a closed trade to the Trade Logs worksheet."""
        if not self.trades_sheet:
            return

        try:
            row = [
                trade.get("trade_id", ""),
                trade.get("exit_time", trade.get("entry_time", "")),
                trade.get("symbol", ""),
                trade.get("signal", ""),
                trade.get("entry_price", 0.0),
                trade.get("exit_price", 0.0),
                trade.get("quantity", 0),
                trade.get("pnl", 0.0),
                f"{trade.get('pnl_percent', 0.0)}%",
                trade.get("exit_reason", ""),
                trade.get("status", "CLOSED")
            ]
            self.trades_sheet.append_row(row)
            print(f"[GoogleSheets] Synced trade {trade.get('trade_id')} to Google Sheet!")
        except Exception as e:
            print(f"[GoogleSheets] Failed to log trade: {e}")

    def update_daily_summary(
        self,
        date_str: str,
        total_trades: int,
        wins: int,
        losses: int,
        win_rate: float,
        daily_pnl: float,
        closing_balance: float
    ):
        """Appends/updates the day's performance summary."""
        if not self.daily_sheet:
            return

        try:
            row = [
                date_str,
                total_trades,
                wins,
                losses,
                f"{win_rate:.2f}%",
                round(daily_pnl, 2),
                round(closing_balance, 2)
            ]
            self.daily_sheet.append_row(row)
            print(f"[GoogleSheets] Updated Daily Summary for {date_str}!")
        except Exception as e:
            print(f"[GoogleSheets] Failed to update daily summary: {e}")
