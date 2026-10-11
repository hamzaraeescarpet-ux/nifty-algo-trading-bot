import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return atr

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    Calculates Supertrend indicator.
    Returns DataFrame with columns:
    - Supertrend: Current supertrend value
    - Supertrend_Direction: 1 for Bullish (Green), -1 for Bearish (Red)
    """
    atr = calculate_atr(df, period)
    hl2 = (df['High'] + df['Low']) / 2
    
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    
    close = df['Close'].values
    b_up = basic_upper.values
    b_low = basic_lower.values
    f_up = np.zeros(len(df))
    f_low = np.zeros(len(df))
    st = np.zeros(len(df))
    direction = np.zeros(len(df), dtype=int)
    
    for i in range(1, len(df)):
        # Final Upper Band
        if b_up[i] < f_up[i-1] or close[i-1] > f_up[i-1]:
            f_up[i] = b_up[i]
        else:
            f_up[i] = f_up[i-1]
            
        # Final Lower Band
        if b_low[i] > f_low[i-1] or close[i-1] < f_low[i-1]:
            f_low[i] = b_low[i]
        else:
            f_low[i] = f_low[i-1]
            
        # Trend Direction
        if i == 1:
            direction[i] = 1 if close[i] > f_up[i] else -1
        else:
            if direction[i-1] == 1 and close[i] < f_low[i]:
                direction[i] = -1
            elif direction[i-1] == -1 and close[i] > f_up[i]:
                direction[i] = 1
            else:
                direction[i] = direction[i-1]
                
        st[i] = f_low[i] if direction[i] == 1 else f_up[i]
        
    res = pd.DataFrame(index=df.index)
    res['Supertrend'] = st
    res['Supertrend_Direction'] = direction
    return res

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculates Volume Weighted Average Price (VWAP).
    Anchors to each intraday session if Datetime index is available.
    """
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    volume = df['Volume']
    
    if isinstance(df.index, pd.DatetimeIndex):
        # Anchor per date
        dates = df.index.date
        tp_v = typical_price * volume
        cum_tp_v = tp_v.groupby(dates).cumsum()
        cum_v = volume.groupby(dates).cumsum()
        vwap = cum_tp_v / cum_v.replace(0, np.nan)
        return vwap.fillna(typical_price)
    else:
        cum_tp_v = (typical_price * volume).cumsum()
        cum_v = volume.cumsum()
        return cum_tp_v / cum_v.replace(0, np.nan)

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Average Directional Index (ADX) to filter out sideways choppy markets."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan))
    
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return adx.fillna(20.0)

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Calculates MACD Line, Signal Line, and MACD Histogram."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    res = pd.DataFrame(index=series.index)
    res['MACD'] = macd_line
    res['MACD_Signal'] = signal_line
    res['MACD_Hist'] = macd_hist
    return res
