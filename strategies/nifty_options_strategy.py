import pandas as pd
from typing import Dict, Any, Optional
from strategies.confluence_strategy import ConfluenceStrategy
from config import settings

class NiftyOptionsStrategy:
    """
    Translates Nifty 50 Index Confluence Signals into ATM Options Contracts:
    - Bullish Signal -> Buys ATM CALL (CE)
    - Bearish Signal -> Buys ATM PUT (PE)
    - Automatically calculates ATM Strike, Option Premium, Delta SL & Targets.
    """
    def __init__(self, config=settings):
        self.config = config
        self.base_strategy = ConfluenceStrategy(config=config)

    def get_atm_strike(self, spot_price: float) -> int:
        """Finds the closest ATM Strike rounded to 50 points."""
        step = self.config.ATM_STRIKE_STEP
        return int(round(spot_price / step) * step)

    def estimate_atm_premium(self, spot_price: float, atr: float) -> float:
        """
        Estimates realistic ATM option premium based on market volatility.
        ATM Premium ~ 0.65% to 0.8% of Spot price for weekly options.
        """
        base_pct = 0.0070
        estimated_premium = spot_price * base_pct
        return round(max(50.0, estimated_premium), 1)

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

        # Option Premium modeling
        option_entry_price = self.estimate_atm_premium(spot_price, atr)
        
        # Calculate Option Stop-Loss & Target using Delta (0.5 for ATM)
        index_risk = abs(spot_price - index_sl)
        option_risk = round(index_risk * self.config.OPTION_DELTA, 1)
        # Cap option risk to maximum 35% of premium to avoid complete capital bleed
        option_risk = min(option_risk, option_entry_price * 0.35)

        option_sl = round(max(5.0, option_entry_price - option_risk), 1)
        option_target = round(option_entry_price + (option_risk * self.config.RISK_REWARD_RATIO), 1)

        return {
            "signal": "BUY",  # We always BUY options (either Call or Put)
            "option_action": f"BUY_{option_type}",
            "instrument": contract_name,
            "underlying_symbol": "^NSEI",
            "underlying_price": spot_price,
            "strike": atm_strike,
            "option_type": option_type,
            "price": option_entry_price,
            "stop_loss": option_sl,
            "target": option_target,
            "option_risk_per_share": option_risk,
            "index_atr": atr,
            "lot_size": self.config.OPTION_LOT_SIZE,
            "reason": f"Nifty Index {direction} -> {contract_name} Triggered ({index_signal['reason']})"
        }
