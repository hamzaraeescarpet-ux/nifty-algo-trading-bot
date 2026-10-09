import pandas as pd
from typing import Dict, Any, Optional
from strategies.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_supertrend,
    calculate_vwap
)
from config import settings

class ConfluenceStrategy:
    """
    Advanced Intraday Confluence Strategy:
    Combines Supertrend + VWAP + Dual EMA Trend Filter + RSI Momentum + ATR Volatility SL.
    Aims for high win-rate with minimum drawdown through strict multi-factor filters.
    """
    def __init__(self, config=settings):
        self.config = config

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes all required technical indicators onto the candle dataframe."""
        df = df.copy()
        
        # 1. EMAs
        df['EMA_FAST'] = calculate_ema(df['Close'], self.config.EMA_FAST)
        df['EMA_SLOW'] = calculate_ema(df['Close'], self.config.EMA_SLOW)
        
        # 2. RSI
        df['RSI'] = calculate_rsi(df['Close'], self.config.RSI_PERIOD)
        
        # 3. ATR
        df['ATR'] = calculate_atr(df, self.config.ATR_PERIOD)
        
        # 4. Supertrend
        st_df = calculate_supertrend(
            df,
            period=self.config.SUPERTREND_PERIOD,
            multiplier=self.config.SUPERTREND_MULTIPLIER
        )
        df['Supertrend'] = st_df['Supertrend']
        df['Supertrend_Direction'] = st_df['Supertrend_Direction']
        
        # 5. VWAP
        df['VWAP'] = calculate_vwap(df)
        
        return df

    def analyze_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Analyzes the latest closed candle to detect Buy/Sell trade signal.
        Returns signal dictionary if conditions are met, else None.
        """
        if len(df) < max(self.config.EMA_SLOW, self.config.RSI_PERIOD, self.config.ATR_PERIOD) + 2:
            return None
            
        df = self.populate_indicators(df)
        
        # We look at the latest completed candle (index -1)
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = curr['Close']
        atr = curr['ATR']
        
        if pd.isna(atr) or atr <= 0:
            return None

        # --- BUY (LONG) CONDITIONS ---
        # 1. Supertrend is Bullish (Green)
        # 2. Price is above VWAP
        # 3. EMA 20 is above EMA 50 and Price > EMA 20
        # 4. RSI is in healthy bullish momentum zone (e.g. 52 - 68)
        is_bullish_trend = (
            curr['Supertrend_Direction'] == 1 and
            close > curr['VWAP'] and
            curr['EMA_FAST'] > curr['EMA_SLOW'] and
            close > curr['EMA_FAST']
        )
        is_bullish_momentum = (
            self.config.RSI_BUY_MIN <= curr['RSI'] <= self.config.RSI_BUY_MAX
        )
        
        # Entry trigger: Fresh trend confirmation (Supertrend flipped OR EMA crossover OR fresh bounce above VWAP)
        bullish_trigger = (
            (prev['Supertrend_Direction'] != 1 and curr['Supertrend_Direction'] == 1) or
            (prev['Close'] <= prev['VWAP'] and curr['Close'] > curr['VWAP']) or
            (prev['Close'] <= prev['EMA_FAST'] and curr['Close'] > curr['EMA_FAST'])
        )

        if is_bullish_trend and is_bullish_momentum and bullish_trigger:
            stop_loss = round(close - (self.config.ATR_SL_MULTIPLIER * atr), 2)
            risk = close - stop_loss
            target = round(close + (self.config.RISK_REWARD_RATIO * risk), 2)
            
            return {
                "signal": "BUY",
                "price": round(close, 2),
                "stop_loss": stop_loss,
                "target": target,
                "atr": round(atr, 2),
                "rsi": round(curr['RSI'], 2),
                "supertrend": round(curr['Supertrend'], 2),
                "vwap": round(curr['VWAP'], 2),
                "reason": "Bullish Confluence: ST Green + VWAP + EMA 20>50 + RSI Momentum"
            }

        # --- SELL (SHORT) CONDITIONS ---
        # 1. Supertrend is Bearish (Red)
        # 2. Price is below VWAP
        # 3. EMA 20 is below EMA 50 and Price < EMA 20
        # 4. RSI is in healthy bearish momentum zone (e.g. 32 - 48)
        is_bearish_trend = (
            curr['Supertrend_Direction'] == -1 and
            close < curr['VWAP'] and
            curr['EMA_FAST'] < curr['EMA_SLOW'] and
            close < curr['EMA_FAST']
        )
        is_bearish_momentum = (
            self.config.RSI_SELL_MIN <= curr['RSI'] <= self.config.RSI_SELL_MAX
        )
        
        bearish_trigger = (
            (prev['Supertrend_Direction'] != -1 and curr['Supertrend_Direction'] == -1) or
            (prev['Close'] >= prev['VWAP'] and curr['Close'] < curr['VWAP']) or
            (prev['Close'] >= prev['EMA_FAST'] and curr['Close'] < curr['EMA_FAST'])
        )

        if is_bearish_trend and is_bearish_momentum and bearish_trigger:
            stop_loss = round(close + (self.config.ATR_SL_MULTIPLIER * atr), 2)
            risk = stop_loss - close
            target = round(close - (self.config.RISK_REWARD_RATIO * risk), 2)
            
            return {
                "signal": "SELL",
                "price": round(close, 2),
                "stop_loss": stop_loss,
                "target": target,
                "atr": round(atr, 2),
                "rsi": round(curr['RSI'], 2),
                "supertrend": round(curr['Supertrend'], 2),
                "vwap": round(curr['VWAP'], 2),
                "reason": "Bearish Confluence: ST Red + Below VWAP + EMA 20<50 + RSI Momentum"
            }

        return None
