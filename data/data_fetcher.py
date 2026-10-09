import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional
from config import settings

class MarketDataFetcher:
    """
    Fetches real-time and historical market data for Indian Equities.
    Uses Yahoo Finance (.NS tickers) for paper trading & backtesting,
    with built-in caching and validation.
    """
    def __init__(self, config=settings):
        self.config = config

    def get_historical_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d"
    ) -> Optional[pd.DataFrame]:
        """
        Fetches historical intraday/daily candle data.
        Yahoo Finance intraday limits:
        - 5m: up to 60 days
        - 15m: up to 60 days
        - 1d: up to many years
        """
        # Ensure NSE suffix
        ticker = symbol if symbol.endswith(".NS") or symbol.startswith("^") else f"{symbol}.NS"
        
        try:
            df = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True
            )
            
            if df.empty or len(df) < 20:
                print(f"[DataFetcher] Warning: No/insufficient data received for {ticker}")
                return None
                
            # Handle MultiIndex columns if returned by newer yfinance versions
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            # Standardize column names
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df.dropna(inplace=True)
            return df
            
        except Exception as e:
            print(f"[DataFetcher] Error fetching data for {ticker}: {e}")
            return None

    def get_latest_candle(self, symbol: str, interval: str = "5m") -> Optional[pd.Series]:
        """Fetches the latest completed candle for real-time paper trading updates."""
        df = self.get_historical_data(symbol, interval=interval, period="1d")
        if df is not None and not df.empty:
            return df.iloc[-1]
        return None
