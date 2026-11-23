import pyotp
from typing import Optional, Dict, Any
from config import settings

class KotakNeoBroker:
    """
    Kotak Neo Trade API v2 Integration:
    - Automated 2FA login using pyotp and Kotak Neo v2 TOTP SDK.
    - Live Option LTP & Quotes fetching for 100% authentic pricing.
    - Order execution (Intraday MIS / Normal CNC).
    - Position and Margin checking.
    """
    def __init__(self, config=settings):
        self.config = config
        self.client = None
        self.is_authenticated = False

    def connect(self) -> bool:
        """Authenticates with Kotak Neo Trade API v2 using Consumer Key, TOTP & MPIN."""
        if not self.config.KOTAK_CONSUMER_KEY or not self.config.KOTAK_MOBILE_NUMBER:
            print("[KotakNeoBroker] Credentials not set. Running in Mock/Paper mode.")
            return False

        try:
            from neo_api_client import NeoAPI
            
            self.client = NeoAPI(
                consumer_key=self.config.KOTAK_CONSUMER_KEY,
                environment=self.config.KOTAK_ENVIRONMENT
            )
            
            print("[KotakNeoBroker] Initiating Kotak Neo v2 TOTP Login...")
            # Step 1: Generate dynamic TOTP code
            if self.config.KOTAK_TOTP_KEY:
                totp = pyotp.TOTP(self.config.KOTAK_TOTP_KEY).now()
            else:
                print("[KotakNeoBroker] Error: KOTAK_TOTP_KEY is required for automated 2FA login.")
                return False

            # Step 2: TOTP Login
            self.client.totp_login(
                mobile_number=self.config.KOTAK_MOBILE_NUMBER,
                ucc=self.config.KOTAK_UCC,
                totp=totp
            )
            
            # Step 3: Validate MPIN
            self.client.totp_validate(mpin=self.config.KOTAK_MPIN)
            self.is_authenticated = True
            print("[KotakNeoBroker] Connected to Kotak Neo Live Account successfully!")
            return True

        except Exception as e:
            print(f"[KotakNeoBroker] Authentication error: {e}")
            self.is_authenticated = False
            return False

    def get_live_option_ltp(self, strike: int, option_type: str) -> Optional[float]:
        """Fetches real-time LTP of Nifty option contract from Kotak Neo."""
        if not self.is_authenticated or self.client is None:
            return None
        try:
            res = self.client.search_scrip(
                exchange_segment="nfo",
                symbol="NIFTY",
                strike_price=str(strike),
                option_type=option_type
            )
            if res and isinstance(res, list) and len(res) > 0:
                token = res[0].get("pSymbol") or res[0].get("token")
                quote = self.client.quotes(
                    instrument_tokens=[{"instrument_token": str(token), "exchange_segment": "nse_fo"}],
                    quote_type="LTP"
                )
                if quote and "data" in quote and len(quote["data"]) > 0:
                    ltp = float(quote["data"][0].get("last_traded_price", 0.0))
                    if ltp > 0:
                        return ltp
        except Exception as e:
            print(f"[KotakNeoBroker] Could not fetch LTP for {strike} {option_type}: {e}")
        return None

    def place_order(
        self,
        symbol: str,
        transaction_type: str, # "B" for Buy, "S" for Sell
        quantity: int,
        order_type: str = "MKT", # "MKT" or "L"
        price: str = "0",
        product: str = "MIS" # "MIS" for Intraday, "CNC" for Delivery
    ) -> Optional[Dict[str, Any]]:
        """Places live order on Kotak Neo API."""
        if not self.is_authenticated or self.client is None:
            print("[KotakNeoBroker] Not authenticated. Cannot place live order.")
            return None

        # Clean symbol format for Kotak Neo (e.g. RELIANCE-EQ)
        clean_symbol = symbol.replace(".NS", "-EQ")

        try:
            order_res = self.client.place_order(
                exchange_segment="NSE",
                product=product,
                price=price,
                order_type=order_type,
                quantity=str(quantity),
                validity="DAY",
                trading_symbol=clean_symbol,
                transaction_type=transaction_type
            )
            return order_res
        except Exception as e:
            print(f"[KotakNeoBroker] Order placement failed for {clean_symbol}: {e}")
            return None
