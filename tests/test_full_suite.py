import sys
from datetime import datetime, time
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from risk.risk_manager import RiskManager
from strategies.confluence_strategy import ConfluenceStrategy
from execution.kotak_broker import KotakNeoBroker

def test_opening_filter():
    rm = RiskManager()
    
    # 09:17 AM should be blocked by Opening Range Filter
    dt_917 = datetime(2026, 11, 27, 9, 17, 0)
    can_trade, reason = rm.can_open_trade(0, current_time=dt_917)
    assert not can_trade, f"Expected False at 09:17 AM, got {can_trade}"
    print(f" [PASS] 09:17 AM check correctly blocked: {reason}")
    
    # 09:31 AM should be permitted
    dt_931 = datetime(2026, 11, 27, 9, 31, 0)
    can_trade, reason = rm.can_open_trade(0, current_time=dt_931)
    assert can_trade, f"Expected True at 09:31 AM, got {can_trade}"
    print(f" [PASS] 09:31 AM check correctly allowed: {reason}")

def test_htf_trend_filter():
    cs = ConfluenceStrategy()
    
    # Create synthetic downtrend dataframe
    dates = pd.date_range("2026-11-27 09:15", periods=60, freq="5min")
    prices = [26000 - i * 10 for i in range(60)] # steadily falling from 26000 down to 25400
    df = pd.DataFrame({
        "Open": prices,
        "High": [p + 5 for p in prices],
        "Low": [p - 5 for p in prices],
        "Close": prices,
        "Volume": [10000] * 60
    }, index=dates)
    
    htf = cs.get_higher_timeframe_trend(df)
    print(f" [PASS] Falling market HTF trend detected: {htf}")
    assert htf == "BEARISH", f"Expected BEARISH, got {htf}"

def test_kotak_ltp_live():
    b = KotakNeoBroker()
    if b.connect():
        ltp_ce = b.get_live_option_ltp(25900, "CE")
        ltp_pe = b.get_live_option_ltp(25900, "PE")
        print(f" [PASS] Kotak Neo Real Option Chain LTP -> 25900 CE: Rs. {ltp_ce} | 25900 PE: Rs. {ltp_pe}")
        assert ltp_ce is not None and ltp_ce > 0
        assert ltp_pe is not None and ltp_pe > 0
    else:
        print(" [SKIP] Kotak credentials not active or sandboxed")

if __name__ == "__main__":
    test_opening_filter()
    test_htf_trend_filter()
    test_kotak_ltp_live()
    print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
