import pandas as pd
from typing import Dict, Any, Optional
from strategies.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_supertrend,
    calculate_vwap,
    calculate_adx,
    calculate_macd
)
from config import settings

class ConfluenceStrategy:
    """
    Advanced Institutional Confluence Strategy:
    - Directional Alignment: Supertrend (10, 3) + Dual EMA Ribbon (20 & 50)
    - Value Benchmark: VWAP
    - Trend Strength Filter: ADX >= 20 (Blocks sideways choppy market losses)
    - Momentum Acceleration: MACD Histogram + Dynamic RSI
    - Volatility Risk: ATR Volatility Stop Loss
    """
    def __init__(self, config=settings):
        self.config = config

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes all required technical indicators onto the candle dataframe."""
        df = df.copy()
        
        # 1. Dual EMAs
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
        
        # 6. ADX (Trend Strength)
        df['ADX'] = calculate_adx(df, self.config.ADX_PERIOD)
        
        # 7. MACD (Momentum Confirmation)
        macd_df = calculate_macd(
            df['Close'],
            fast=self.config.MACD_FAST,
            slow=self.config.MACD_SLOW,
            signal=self.config.MACD_SIGNAL
        )
        df['MACD'] = macd_df['MACD']
        df['MACD_Signal'] = macd_df['MACD_Signal']
        df['MACD_Hist'] = macd_df['MACD_Hist']
        
        return df

    def analyze_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Analyzes the latest completed candle for high-probability Institutional setups.
        """
        min_bars = max(self.config.EMA_SLOW, self.config.MACD_SLOW, self.config.RSI_PERIOD, self.config.ADX_PERIOD) + 5
        if len(df) < min_bars:
            return None
            
        df = self.populate_indicators(df)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = float(curr['Close'])
        atr = float(curr['ATR'])
        adx = float(curr['ADX'])
        
        if pd.isna(atr) or atr <= 0:
            return None

        # Filter out sideways / dead market: Only trade when ADX confirms trend strength
        has_trend_strength = (adx >= self.config.ADX_MIN_THRESHOLD)
        if not has_trend_strength:
            return None

        # --- BUY (LONG / CALL CE) CONDITIONS ---
        # 1. Supertrend is Green
        # 2. Price > VWAP
        # 3. EMA 20 > EMA 50 and Close > EMA 20
        # 4. RSI is in healthy bullish momentum zone (50 - 70)
        # 5. MACD Histogram is positive (Momentum expanding upwards)
        is_bullish_trend = (
            curr['Supertrend_Direction'] == 1 and
            close > curr['VWAP'] and
            curr['EMA_FAST'] > curr['EMA_SLOW'] and
            close > curr['EMA_FAST'] and
            curr['MACD_Hist'] > 0
        )
        is_bullish_momentum = (
            self.config.RSI_BUY_MIN <= curr['RSI'] <= self.config.RSI_BUY_MAX
        )
        
        # High quality entry trigger: Fresh Supertrend flip OR MACD Histogram expanding OR Break above VWAP
        bullish_trigger = (
            (prev['Supertrend_Direction'] != 1 and curr['Supertrend_Direction'] == 1) or
            (prev['MACD_Hist'] <= 0 and curr['MACD_Hist'] > 0) or
            (prev['Close'] <= prev['VWAP'] and curr['Close'] > curr['VWAP'])
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
                "adx": round(adx, 1),
                "rsi": round(curr['RSI'], 1),
                "supertrend": round(curr['Supertrend'], 2),
                "vwap": round(curr['VWAP'], 2),
                "reason": f"Bullish Confluence: ST Green + VWAP + EMA 20>50 + ADX {adx:.1f} + MACD Bullish"
            }

        # --- SELL (SHORT / PUT PE) CONDITIONS ---
        # 1. Supertrend is Red
        # 2. Price < VWAP
        # 3. EMA 20 < EMA 50 and Close < EMA 20
        # 4. RSI is in healthy bearish momentum zone (30 - 50)
        # 5. MACD Histogram is negative (Momentum expanding downwards)
        is_bearish_trend = (
            curr['Supertrend_Direction'] == -1 and
            close < curr['VWAP'] and
            curr['EMA_FAST'] < curr['EMA_SLOW'] and
            close < curr['EMA_FAST'] and
            curr['MACD_Hist'] < 0
        )
        is_bearish_momentum = (
            self.config.RSI_SELL_MIN <= curr['RSI'] <= self.config.RSI_SELL_MAX
        )
        
        # High quality entry trigger: Fresh Supertrend flip OR MACD Histogram drop OR Break below VWAP
        bearish_trigger = (
            (prev['Supertrend_Direction'] != -1 and curr['Supertrend_Direction'] == -1) or
            (prev['MACD_Hist'] >= 0 and curr['MACD_Hist'] < 0) or
            (prev['Close'] >= prev['VWAP'] and curr['Close'] < curr['VWAP'])
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
                "adx": round(adx, 1),
                "rsi": round(curr['RSI'], 1),
                "supertrend": round(curr['Supertrend'], 2),
                "vwap": round(curr['VWAP'], 2),
                "reason": f"Bearish Confluence: ST Red + VWAP + EMA 20<50 + ADX {adx:.1f} + MACD Bearish"
            }

        return None
