from typing import Tuple, Dict, Any
from config import settings

class RiskManager:
    """
    Institutional Risk Management Engine:
    - Protects capital with Max Daily Loss circuit breaker.
    - Mathematical position sizing based on risk per trade.
    - Dynamic Trailing Stop-Loss to lock in profits.
    """
    def __init__(self, initial_capital: float = settings.INITIAL_CAPITAL, config=settings):
        self.config = config
        self.capital = initial_capital
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.max_daily_loss = initial_capital * (self.config.MAX_DAILY_LOSS_PERCENT / 100.0)
        self.risk_per_trade_amount = initial_capital * (self.config.RISK_PER_TRADE_PERCENT / 100.0)
        self.is_circuit_breaker_tripped = False

    def reset_daily_metrics(self):
        """Resets PnL counters at the start of a new trading day."""
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.is_circuit_breaker_tripped = False

    def increment_trade_count(self):
        """Increments daily executed trades counter."""
        self.daily_trades_count += 1

    def update_daily_pnl(self, realized_pnl: float):
        """Updates daily PnL and triggers circuit breaker if loss limit is breached."""
        self.daily_pnl += realized_pnl
        self.capital += realized_pnl
        # Recalculate dynamic risk amounts based on updated capital
        self.max_daily_loss = self.capital * (self.config.MAX_DAILY_LOSS_PERCENT / 100.0)
        self.risk_per_trade_amount = self.capital * (self.config.RISK_PER_TRADE_PERCENT / 100.0)

        if self.daily_pnl <= -self.max_daily_loss:
            self.is_circuit_breaker_tripped = True

    def can_open_trade(self, open_positions_count: int) -> Tuple[bool, str]:
        """Validates whether a new trade can be opened according to risk rules."""
        if self.is_circuit_breaker_tripped:
            return False, f"Daily Max Loss Limit reached (Rs. {abs(self.daily_pnl):.2f} / Rs. {self.max_daily_loss:.2f}). Trading paused for today."

        max_daily_trades = getattr(self.config, 'MAX_DAILY_TRADES', 3)
        if self.daily_trades_count >= max_daily_trades:
            return False, f"Maximum daily trade limit ({max_daily_trades}) reached. Preserving daily capital."
            
        if open_positions_count >= self.config.MAX_OPEN_POSITIONS:
            return False, f"Maximum allowed open positions ({self.config.MAX_OPEN_POSITIONS}) already reached."
            
        return True, "Trade allowed"

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Calculates exact quantity of shares based on fixed fractional risk.
        Quantity = Risk Amount / Per Share Risk
        """
        per_share_risk = abs(entry_price - stop_loss)
        if per_share_risk <= 0:
            return 0
            
        qty = int(self.risk_per_trade_amount / per_share_risk)
        
        # Also ensure we don't exceed available capital
        max_possible_qty = int(self.capital / entry_price)
        final_qty = max(1, min(qty, max_possible_qty))
        return final_qty

    def check_trailing_stop(
        self,
        position: Dict[str, Any],
        current_price: float,
        high_price: float = None,
        low_price: float = None
    ) -> Tuple[bool, float]:
        """
        Dynamic Profit-Locking & High-Watermark Trailing Stop:
        - Tracks peak favorable excursion (candle high for BUY / candle low for SELL).
        - Stage 1 (Fast Capital Shield): Gain >= +0.35R -> Trail SL to Breakeven (0 risk).
        - Stage 2 (Lock Profit 1): Gain >= +0.6R (~12 pts) -> Lock in +0.3R guaranteed profit.
        - Stage 3 (Lock Profit 2): Gain >= +1.0R (~20 pts) -> Lock in +0.65R guaranteed profit (e.g. 198 rally locks ~189).
        - Stage 4 (Trend Runner): Gain >= +1.5R -> Lock in +1.1R guaranteed profit.
        - Stage 5 (Dynamic Watermark): Gain >= +1.8R -> Trail SL at Peak - (0.35 * initial_risk).
        """
        direction = position.get('signal', 'BUY')
        entry_price = float(position['entry_price'])
        curr_sl = float(position['stop_loss'])
        initial_sl = float(position.get('initial_sl', curr_sl))
        initial_risk = abs(entry_price - initial_sl)
        
        if initial_risk <= 0:
            return False, curr_sl

        if direction == "BUY":
            peak_price = max(
                current_price,
                high_price if high_price is not None else current_price,
                float(position.get("highest_price", current_price))
            )
            gain = peak_price - entry_price
            new_sl = curr_sl

            if gain >= 1.8 * initial_risk:
                candidate = round(peak_price - (0.35 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            elif gain >= 1.5 * initial_risk:
                candidate = round(entry_price + (1.1 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            elif gain >= 1.0 * initial_risk:
                candidate = round(entry_price + (0.65 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            elif gain >= 0.6 * initial_risk:
                candidate = round(entry_price + (0.3 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            elif gain >= 0.35 * initial_risk:
                candidate = round(entry_price, 1)
                new_sl = max(new_sl, candidate)

            if new_sl > curr_sl:
                return True, new_sl

        elif direction == "SELL":
            lowest_seen = min(
                current_price,
                low_price if low_price is not None else current_price,
                float(position.get("lowest_price", current_price))
            )
            gain = entry_price - lowest_seen
            new_sl = curr_sl

            if gain >= 1.8 * initial_risk:
                candidate = round(lowest_seen + (0.35 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 1.5 * initial_risk:
                candidate = round(entry_price - (1.1 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 1.0 * initial_risk:
                candidate = round(entry_price - (0.65 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 0.6 * initial_risk:
                candidate = round(entry_price - (0.3 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 0.35 * initial_risk:
                candidate = round(entry_price, 1)
                new_sl = min(new_sl, candidate)

            if new_sl < curr_sl:
                return True, new_sl

        return False, curr_sl
