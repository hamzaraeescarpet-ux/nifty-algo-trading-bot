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
        self.max_daily_loss = initial_capital * (self.config.MAX_DAILY_LOSS_PERCENT / 100.0)
        self.risk_per_trade_amount = initial_capital * (self.config.RISK_PER_TRADE_PERCENT / 100.0)
        self.is_circuit_breaker_tripped = False

    def reset_daily_metrics(self):
        """Resets PnL counters at the start of a new trading day."""
        self.daily_pnl = 0.0
        self.is_circuit_breaker_tripped = False

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

    def check_trailing_stop(self, position: Dict[str, Any], current_price: float) -> Tuple[bool, float]:
        """
        Checks and updates trailing stop-loss.
        If trade reaches 1R profit, move SL to breakeven (entry price).
        If trade reaches beyond 1.5R, trail SL by 1.5 * ATR.
        Returns: (is_updated, new_sl)
        """
        direction = position['signal'] # BUY or SELL
        entry_price = position['entry_price']
        curr_sl = position['stop_loss']
        atr = position.get('atr', (abs(entry_price - curr_sl) / self.config.ATR_SL_MULTIPLIER))
        initial_risk = abs(entry_price - position['initial_sl'])
        
        if direction == "BUY":
            gain = current_price - entry_price
            # If gain >= 1R, lock breakeven
            if gain >= initial_risk and curr_sl < entry_price:
                return True, entry_price
            # If gain >= 1.5R, trail behind price
            if gain >= 1.5 * initial_risk:
                potential_sl = round(current_price - (self.config.ATR_SL_MULTIPLIER * atr), 2)
                if potential_sl > curr_sl:
                    return True, potential_sl
                    
        elif direction == "SELL":
            gain = entry_price - current_price
            # If gain >= 1R, lock breakeven
            if gain >= initial_risk and curr_sl > entry_price:
                return True, entry_price
            # If gain >= 1.5R, trail above price
            if gain >= 1.5 * initial_risk:
                potential_sl = round(current_price + (self.config.ATR_SL_MULTIPLIER * atr), 2)
                if potential_sl < curr_sl:
                    return True, potential_sl
                    
        return False, curr_sl
