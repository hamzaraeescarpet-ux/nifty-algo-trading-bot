from typing import Tuple, Dict, Any, Optional
from datetime import datetime
from config import settings

class RiskManager:
    """
    Institutional Risk Management Engine:
    - Protects capital with Max Daily Loss circuit breaker.
    - Mathematical position sizing based on risk per trade.
    - Dynamic Trailing Stop-Loss with generous option breathing room.
    - Anti-Whipsaw Re-Entry Cooldown to prevent duplicate/chasing trades.
    """
    def __init__(self, initial_capital: float = settings.INITIAL_CAPITAL, config=settings):
        self.config = config
        self.capital = initial_capital
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.max_daily_loss = initial_capital * (self.config.MAX_DAILY_LOSS_PERCENT / 100.0)
        self.risk_per_trade_amount = initial_capital * (self.config.RISK_PER_TRADE_PERCENT / 100.0)
        self.is_circuit_breaker_tripped = False
        self.last_exit_time: Optional[datetime] = None
        self.cooldown_minutes: int = 15  # Wait 15 mins (3 candles) after exit before re-entering

    def reset_daily_metrics(self):
        """Resets PnL counters at the start of a new trading day."""
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.is_circuit_breaker_tripped = False
        self.last_exit_time = None

    def increment_trade_count(self):
        """Increments daily executed trades counter."""
        self.daily_trades_count += 1

    def register_trade_exit(self, exit_time: Optional[datetime] = None):
        """Records the time a trade closed to enforce anti-whipsaw cooldown."""
        self.last_exit_time = exit_time if exit_time else datetime.now()

    def update_daily_pnl(self, realized_pnl: float):
        """Updates daily PnL and triggers circuit breaker if loss limit is breached."""
        self.daily_pnl += realized_pnl
        self.capital += realized_pnl
        self.max_daily_loss = self.capital * (self.config.MAX_DAILY_LOSS_PERCENT / 100.0)
        self.risk_per_trade_amount = self.capital * (self.config.RISK_PER_TRADE_PERCENT / 100.0)

        if self.daily_pnl <= -self.max_daily_loss:
            self.is_circuit_breaker_tripped = True

    def can_open_trade(self, open_positions_count: int, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """Validates whether a new trade can be opened according to risk & cooldown rules."""
        if self.is_circuit_breaker_tripped:
            return False, f"Daily Max Loss Limit reached (Rs. {abs(self.daily_pnl):.2f} / Rs. {self.max_daily_loss:.2f}). Trading paused for today."

        max_daily_trades = getattr(self.config, 'MAX_DAILY_TRADES', 3)
        if self.daily_trades_count >= max_daily_trades:
            return False, f"Maximum daily trade limit ({max_daily_trades}) reached. Preserving daily capital."
            
        if open_positions_count >= self.config.MAX_OPEN_POSITIONS:
            return False, f"Maximum allowed open positions ({self.config.MAX_OPEN_POSITIONS}) already reached."

        # Anti-Whipsaw Cooldown: Prevent re-entering right after a trade closed
        if self.last_exit_time:
            now = current_time if current_time else datetime.now()
            elapsed_mins = (now - self.last_exit_time).total_seconds() / 60.0
            if elapsed_mins < self.cooldown_minutes:
                rem = max(1, int(self.cooldown_minutes - elapsed_mins))
                return False, f"Anti-whipsaw cooldown active ({rem} mins left after last trade exit). Awaiting fresh market structure."
            
        return True, "Trade allowed"

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """Calculates exact quantity based on fixed fractional risk."""
        per_share_risk = abs(entry_price - stop_loss)
        if per_share_risk <= 0:
            return 0
            
        qty = int(self.risk_per_trade_amount / per_share_risk)
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
        Dynamic Profit-Locking & Breathing Room Trailing Stop:
        - Avoids choking trades with premature breakeven at 5-6 points noise.
        - Stage 1 (Risk Reduction @ +0.5R, ~8-10 pts): Reduces risk to -0.4R while leaving breathing room.
        - Stage 2 (Breakeven @ +0.8R, ~13-15 pts): Moves SL to Cost-to-Cost (0 Risk).
        - Stage 3 (Lock Profit 1 @ +1.1R, ~18-20 pts): Locks in +0.5R guaranteed profit.
        - Stage 4 (Lock Profit 2 @ +1.5R, ~25 pts): Locks in +1.0R guaranteed profit.
        - Stage 5 (Dynamic Runner @ +2.0R+): Trails dynamically at Peak - (0.4 * initial_risk).
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

            # Stage 5: Dynamic Runner (Huge expansion)
            if gain >= 2.0 * initial_risk:
                candidate = round(peak_price - (0.4 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            # Stage 4: +1.5R reached -> Lock in +1.0R profit
            elif gain >= 1.5 * initial_risk:
                candidate = round(entry_price + (1.0 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            # Stage 3: +1.1R reached -> Lock in +0.5R profit
            elif gain >= 1.1 * initial_risk:
                candidate = round(entry_price + (0.5 * initial_risk), 1)
                new_sl = max(new_sl, candidate)
            # Stage 2: +0.8R reached -> Genuine breakout -> Move to Breakeven
            elif gain >= 0.8 * initial_risk:
                candidate = round(entry_price, 1)
                new_sl = max(new_sl, candidate)
            # Stage 1: +0.5R reached -> Reduce risk to -0.4R (gives room to breathe)
            elif gain >= 0.5 * initial_risk:
                candidate = round(entry_price - (0.4 * initial_risk), 1)
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

            if gain >= 2.0 * initial_risk:
                candidate = round(lowest_seen + (0.4 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 1.5 * initial_risk:
                candidate = round(entry_price - (1.0 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 1.1 * initial_risk:
                candidate = round(entry_price - (0.5 * initial_risk), 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 0.8 * initial_risk:
                candidate = round(entry_price, 1)
                new_sl = min(new_sl, candidate)
            elif gain >= 0.5 * initial_risk:
                candidate = round(entry_price + (0.4 * initial_risk), 1)
                new_sl = min(new_sl, candidate)

            if new_sl < curr_sl:
                return True, new_sl

        return False, curr_sl
