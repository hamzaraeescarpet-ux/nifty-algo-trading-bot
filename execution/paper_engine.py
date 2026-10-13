import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from tabulate import tabulate
from config import settings

class PaperExecutionEngine:
    """
    Realistic Paper Trading Simulator:
    - Maintains virtual balance, margin, and positions.
    - Matches live candle high/low against SL and Target.
    - Saves all closed trades to a persistent journal (JSON & CSV).
    """
    def __init__(self, initial_capital: float = settings.INITIAL_CAPITAL, journal_dir: str = "logs", sheets_sync=None):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.sheets_sync = sheets_sync
        
        # Setup logs directory
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.journal_file = self.journal_dir / "paper_trades_journal.json"
        self._load_journal()

    def _load_journal(self):
        """Loads previous paper trade history if exists."""
        if self.journal_file.exists():
            try:
                with open(self.journal_file, "r") as f:
                    data = json.load(f)
                    self.balance = data.get("balance", self.initial_capital)
                    self.trade_history = data.get("history", [])
            except Exception:
                pass

    def _save_journal(self):
        """Persists current trade history to JSON file."""
        data = {
            "initial_capital": self.initial_capital,
            "balance": self.balance,
            "total_trades": len(self.trade_history),
            "history": self.trade_history,
            "open_positions": list(self.open_positions.values())
        }
        with open(self.journal_file, "w") as f:
            json.dump(data, f, indent=4, default=str)

        try:
            from dashboard.generate_report import generate_static_report
            generate_static_report()
        except Exception:
            pass

    def execute_order(
        self,
        symbol: str,
        signal: str,
        price: float,
        quantity: int,
        stop_loss: float,
        target: float,
        reason: str,
        atr: float
    ) -> Dict[str, Any]:
        now_ist = settings.get_now_ist()
        trade_id = f"TRADE_{len(self.trade_history) + len(self.open_positions) + 1}_{now_ist.strftime('%H%M%S')}"
        position = {
            "trade_id": trade_id,
            "symbol": symbol,
            "signal": signal,
            "entry_time": now_ist.strftime("%d-%b-%Y %H:%M:%S"),
            "entry_price": price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "initial_sl": stop_loss,
            "target": target,
            "atr": atr,
            "reason": reason,
            "status": "OPEN",
            "highest_price": price,
            "lowest_price": price
        }
        self.open_positions[symbol] = position
        self._save_journal()
        return position

    def update_and_check_exits(
        self,
        symbol: str,
        high_price: float,
        low_price: float,
        close_price: float,
        force_square_off: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates candle high/low against Stop-Loss and Target.
        Returns closed trade details if an exit was triggered.
        """
        if symbol not in self.open_positions:
            return None

        pos = self.open_positions[symbol]
        direction = pos["signal"]
        qty = pos["quantity"]
        entry = pos["entry_price"]
        sl = pos["stop_loss"]
        target = pos["target"]
        
        # Track price extremes
        pos["highest_price"] = max(pos["highest_price"], high_price)
        pos["lowest_price"] = min(pos["lowest_price"], low_price)
        
        exit_triggered = False
        exit_price = 0.0
        exit_reason = ""

        # Force End-of-day square-off
        if force_square_off:
            exit_triggered = True
            exit_price = close_price
            exit_reason = "3:15 PM EOD SQUARE_OFF"

        elif direction == "BUY":
            # Target Hit Check
            if high_price >= target:
                exit_triggered = True
                exit_price = target
                exit_reason = "TARGET HIT (PROFIT)"
            # Stop Loss Hit Check
            elif low_price <= sl:
                exit_triggered = True
                exit_price = sl
                exit_reason = "TRAILING SL HIT" if sl > pos["initial_sl"] else "STOP LOSS HIT"

        elif direction == "SELL":
            # Target Hit Check
            if low_price <= target:
                exit_triggered = True
                exit_price = target
                exit_reason = "TARGET HIT (PROFIT)"
            # Stop Loss Hit Check
            elif high_price >= sl:
                exit_triggered = True
                exit_price = sl
                exit_reason = "TRAILING SL HIT" if sl < pos["initial_sl"] else "STOP LOSS HIT"

        if exit_triggered:
            # Calculate PnL
            if direction == "BUY":
                pnl = round((exit_price - entry) * qty, 2)
            else:
                pnl = round((entry - exit_price) * qty, 2)
                
            pnl_pct = round((pnl / (entry * qty)) * 100, 2)
            self.balance += pnl
            
            closed_trade = {
                **pos,
                "exit_time": settings.get_now_ist().strftime("%d-%b-%Y %H:%M:%S"),
                "exit_price": round(exit_price, 2),
                "exit_reason": exit_reason,
                "pnl": pnl,
                "pnl_percent": pnl_pct,
                "status": "CLOSED"
            }
            
            self.trade_history.append(closed_trade)
            del self.open_positions[symbol]
            self._save_journal()

            # Sync to Google Sheets if available
            if self.sheets_sync:
                try:
                    self.sheets_sync.log_trade(closed_trade)
                    self.sheets_sync.update_summaries_from_history(self.trade_history, self.balance, self.initial_capital)
                except Exception as e:
                    print(f"[PaperEngine] Sheet sync error: {e}")

            return closed_trade

        return None

    def update_trailing_sl(self, symbol: str, new_sl: float):
        """Updates the stop-loss for an active position."""
        if symbol in self.open_positions:
            self.open_positions[symbol]["stop_loss"] = new_sl
            self._save_journal()

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates overall performance metrics."""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "balance": self.balance,
                "wins": 0,
                "losses": 0
            }

        wins = [t for t in self.trade_history if t["pnl"] > 0]
        losses = [t for t in self.trade_history if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trade_history)
        win_rate = (len(wins) / len(self.trade_history)) * 100

        return {
            "total_trades": len(self.trade_history),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "balance": round(self.balance, 2)
        }

    def print_performance_table(self):
        """Prints a clean summary table to console."""
        stats = self.get_summary_stats()
        table = [
            ["Initial Capital", f"Rs. {self.initial_capital:,.2f}"],
            ["Current Balance", f"Rs. {stats['balance']:,.2f}"],
            ["Net Realized PnL", f"Rs. {stats['total_pnl']:,.2f}"],
            ["Total Closed Trades", stats["total_trades"]],
            ["Winning Trades", stats["wins"]],
            ["Losing Trades", stats["losses"]],
            ["Win Rate", f"{stats['win_rate']}%"],
            ["Open Positions", len(self.open_positions)]
        ]
        print("\n" + "="*50)
        print("          PAPER TRADING DASHBOARD")
        print("="*50)
        print(tabulate(table, headers=["Metric", "Value"], tablefmt="grid"))
