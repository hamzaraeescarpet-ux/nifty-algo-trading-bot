import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any
from tabulate import tabulate
from strategies.confluence_strategy import ConfluenceStrategy
from risk.risk_manager import RiskManager
from config import settings

class Backtester:
    """
    Simulates strategy execution on historical intraday candles
    with realistic trailing stops, EOD square-offs, and risk controls.
    """
    def __init__(self, initial_capital: float = settings.INITIAL_CAPITAL, config=settings):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.config = config
        self.strategy = ConfluenceStrategy(config=config)
        self.trades: List[Dict[str, Any]] = []

    def run(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Runs the backtest simulation on historical OHLCV data."""
        self.capital = self.initial_capital
        self.trades = []
        risk_manager = RiskManager(initial_capital=self.initial_capital, config=self.config)

        # Precompute indicators
        df = self.strategy.populate_indicators(df)
        
        active_position: Dict[str, Any] = None
        current_date = None

        min_lookback = max(self.config.EMA_SLOW, self.config.RSI_PERIOD, self.config.ATR_PERIOD) + 2

        for i in range(min_lookback, len(df)):
            curr_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            timestamp = df.index[i]
            trade_date = timestamp.date() if hasattr(timestamp, 'date') else None

            # New day reset
            if trade_date != current_date:
                current_date = trade_date
                risk_manager.reset_daily_metrics()

            # Check if active position exists
            if active_position is not None:
                high = curr_row['High']
                low = curr_row['Low']
                close = curr_row['Close']
                direction = active_position['signal']
                entry = active_position['entry_price']
                qty = active_position['quantity']
                sl = active_position['stop_loss']
                target = active_position['target']

                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""

                # Check intraday square-off (3:15 PM)
                time_str = timestamp.strftime("%H:%M") if hasattr(timestamp, 'strftime') else ""
                if time_str >= self.config.SQUARE_OFF_TIME:
                    exit_triggered = True
                    exit_price = close
                    exit_reason = "EOD Square-Off"
                elif direction == "BUY":
                    if high >= target:
                        exit_triggered = True
                        exit_price = target
                        exit_reason = "Target Hit"
                    elif low <= sl:
                        exit_triggered = True
                        exit_price = sl
                        exit_reason = "Trailing SL" if sl > active_position['initial_sl'] else "Stop Loss"
                elif direction == "SELL":
                    if low <= target:
                        exit_triggered = True
                        exit_price = target
                        exit_reason = "Target Hit"
                    elif high >= sl:
                        exit_triggered = True
                        exit_price = sl
                        exit_reason = "Trailing SL" if sl < active_position['initial_sl'] else "Stop Loss"

                if exit_triggered:
                    # Calculate PnL
                    if direction == "BUY":
                        pnl = (exit_price - entry) * qty
                    else:
                        pnl = (entry - exit_price) * qty

                    self.capital += pnl
                    risk_manager.update_daily_pnl(pnl)

                    self.trades.append({
                        "symbol": symbol,
                        "signal": direction,
                        "entry_time": active_position['entry_time'],
                        "entry_price": entry,
                        "exit_time": timestamp,
                        "exit_price": round(exit_price, 2),
                        "quantity": qty,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / (entry * qty)) * 100, 2),
                        "exit_reason": exit_reason,
                        "capital_after": round(self.capital, 2)
                    })
                    active_position = None
                    continue

                # Trailing stop update if still active
                updated, new_sl = risk_manager.check_trailing_stop(active_position, close)
                if updated:
                    active_position['stop_loss'] = new_sl

            # If no active position, check for new entry signal
            if active_position is None:
                can_trade, _ = risk_manager.can_open_trade(0)
                if not can_trade:
                    continue

                sub_df = df.iloc[:i+1]
                signal_data = self.strategy.analyze_signal(sub_df)

                if signal_data is not None:
                    entry_price = signal_data['price']
                    sl = signal_data['stop_loss']
                    target = signal_data['target']
                    atr = signal_data['atr']

                    qty = risk_manager.calculate_position_size(entry_price, sl)
                    if qty > 0:
                        active_position = {
                            "symbol": symbol,
                            "signal": signal_data['signal'],
                            "entry_time": timestamp,
                            "entry_price": entry_price,
                            "quantity": qty,
                            "stop_loss": sl,
                            "initial_sl": sl,
                            "target": target,
                            "atr": atr
                        }

        return self.generate_report(symbol)

    def generate_report(self, symbol: str) -> Dict[str, Any]:
        """Calculates performance report metrics."""
        if not self.trades:
            return {"symbol": symbol, "total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0}

        trades_df = pd.DataFrame(self.trades)
        wins = trades_df[trades_df['pnl'] > 0]
        losses = trades_df[trades_df['pnl'] <= 0]

        total_trades = len(trades_df)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

        gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
        gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
        net_pnl = gross_profit - gross_loss
        return_pct = (net_pnl / self.initial_capital) * 100

        # Max Drawdown calculation
        equity_curve = self.initial_capital + trades_df['pnl'].cumsum()
        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak * 100
        max_drawdown = abs(drawdown.min()) if not drawdown.empty else 0.0

        return {
            "symbol": symbol,
            "initial_capital": self.initial_capital,
            "final_capital": round(self.capital, 2),
            "net_pnl": round(net_pnl, 2),
            "return_pct": round(return_pct, 2),
            "total_trades": total_trades,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "avg_win": round(wins['pnl'].mean(), 2) if not wins.empty else 0.0,
            "avg_loss": round(losses['pnl'].mean(), 2) if not losses.empty else 0.0
        }

    def print_report(self, report: Dict[str, Any]):
        """Prints backtest metrics in a structured table."""
        table = [
            ["Stock Symbol", report["symbol"]],
            ["Initial Capital", f"Rs. {report['initial_capital']:,.2f}"],
            ["Final Capital", f"Rs. {report['final_capital']:,.2f}"],
            ["Net Profit/Loss", f"Rs. {report['net_pnl']:,.2f} ({report['return_pct']}%)"],
            ["Total Trades", report["total_trades"]],
            ["Winning Trades", report["wins"]],
            ["Losing Trades", report["losses"]],
            ["Win Rate", f"{report['win_rate']}%"],
            ["Profit Factor", report["profit_factor"]],
            ["Max Drawdown", f"{report['max_drawdown_pct']}%"],
            ["Average Win", f"Rs. {report['avg_win']:,.2f}"],
            ["Average Loss", f"Rs. {report['avg_loss']:,.2f}"]
        ]
        print("\n" + "="*50)
        print(f"        BACKTEST RESULTS: {report['symbol']}")
        print("="*50)
        print(tabulate(table, headers=["Metric", "Result"], tablefmt="grid"))
