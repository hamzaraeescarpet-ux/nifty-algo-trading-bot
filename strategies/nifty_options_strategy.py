import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional
from strategies.confluence_strategy import ConfluenceStrategy
from config import settings

class NiftyOptionsStrategy:
    """
    Translates Nifty 50 Index Confluence Signals into ATM Options Contracts:
    - Bullish Signal -> Buys ATM CALL (CE)
    - Bearish Signal -> Buys ATM PUT (PE)
    - Fetches Real Live Market LTP via Kotak Neo API when connected.
    - Fallback: Calculates realistic DTE-aware Decay Premium (Mon ~75-85, Thu ~25-35).
    """
    def __init__(self, config=settings, broker=None):
        self.config = config
        self.broker = broker
        self.base_strategy = ConfluenceStrategy(config=config)

    def get_atm_strike(self, spot_price: float) -> int:
        """Finds the closest ATM Strike rounded to 50 points."""
        step = self.config.ATM_STRIKE_STEP
        return int(round(spot_price / step) * step)

    def estimate_atm_premium(self, spot_price: float, atr: float, current_time: Optional[datetime] = None) -> float:
        """
        Calculates realistic ATM option premium based on Day-to-Expiry (DTE) decay:
        Weekly expiry is Thursday (weekday = 3).
        - Friday (DTE 6): ~Rs. 160-180
        - Monday (DTE 3): ~Rs. 75-90 (Matches real market prices!)
        - Tuesday (DTE 2): ~Rs. 60-75
        - Wednesday (DTE 1): ~Rs. 40-55
        - Thursday Expiry (DTE 0): ~Rs. 20-35
        """
        now = current_time if current_time else datetime.now()
        weekday = now.weekday() if hasattr(now, 'weekday') else 0
        
        dte_multipliers = {
            4: 0.0070,  # Friday (far expiry)
            0: 0.0033,  # Monday (~Rs. 75-85 for 25,600 spot)
            1: 0.0026,  # Tuesday (~Rs. 60-70)
            2: 0.0019,  # Wednesday (~Rs. 45-50)
            3: 0.0012   # Thursday Expiry (~Rs. 25-35)
        }
        base_pct = dte_multipliers.get(weekday, 0.0035)
        estimated_premium = spot_price * base_pct
        return round(max(15.0, estimated_premium), 1)

    def generate_option_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Analyzes Nifty 50 Index and returns an Options Trade Contract if signal triggers.
        """
        index_signal = self.base_strategy.analyze_signal(df)
        if not index_signal:
            return None

        spot_price = index_signal["price"]
        index_sl = index_signal["stop_loss"]
        atr = index_signal["atr"]
        direction = index_signal["signal"]

        atm_strike = self.get_atm_strike(spot_price)
        option_type = "CE" if direction == "BUY" else "PE"
        contract_name = f"NIFTY {atm_strike} {option_type}"

        # 1. First priority: Try fetching real-time market LTP from Kotak Neo Broker
        live_ltp = None
        if self.broker and hasattr(self.broker, "get_live_option_ltp"):
            live_ltp = self.broker.get_live_option_ltp(atm_strike, option_type)

        if live_ltp and live_ltp > 5.0:
            option_entry_price = round(live_ltp, 1)
            price_source = "Kotak Neo Live LTP"
        else:
            latest_ts = df.index[-1] if hasattr(df, "index") and not df.empty else None
            option_entry_price = self.estimate_atm_premium(spot_price, atr, current_time=latest_ts)
            price_source = "DTE-Decay Realistic Model"
        
        # Calculate Option Stop-Loss & Target using Delta (0.5 for ATM)
        index_risk = abs(spot_price - index_sl)
        option_risk = round(index_risk * self.config.OPTION_DELTA, 1)
        # Cap option risk to maximum 35% of premium to avoid complete capital bleed
        option_risk = min(option_risk, option_entry_price * 0.35)

        option_sl = round(max(5.0, option_entry_price - option_risk), 1)
        option_target = round(option_entry_price + (option_risk * self.config.RISK_REWARD_RATIO), 1)

        return {
            "signal": "BUY",
            "option_action": f"BUY_{option_type}",
            "instrument": contract_name,
            "underlying_symbol": "^NSEI",
            "underlying_price": spot_price,
            "strike": atm_strike,
            "option_type": option_type,
            "price": option_entry_price,
            "price_source": price_source,
            "stop_loss": option_sl,
            "target": option_target,
            "option_risk_per_share": option_risk,
            "index_atr": atr,
            "lot_size": self.config.OPTION_LOT_SIZE,
            "reason": f"Nifty Index {direction} -> {contract_name} Triggered ({index_signal['reason']})"
        }
