import pyotp
from typing import Optional, Dict, Any
from config import settings

class KotakNeoBroker:
    """
    Kotak Neo Trade API Integration:
    - Automated 2FA login using pyotp.
    - Order execution (Intraday MIS / Normal CNC).
    - Position and Margin checking.
    """
    def __init__(self, config=settings):
        self.config = config
        self.client = None
        self.is_authenticated = False

    def connect(self) -> bool:
        """Authenticates with Kotak Neo Trade API using credentials & TOTP."""
        if not self.config.KOTAK_CONSUMER_KEY or not self.config.KOTAK_MOBILE_NUMBER:
            print("[KotakNeoBroker] Credentials not set in .env. Running in Mock/Paper mode.")
            return False

        try:
            from neo_api_client import NeoAPI
            
            self.client = NeoAPI(
                consumer_key=self.config.KOTAK_CONSUMER_KEY,
                consumer_secret=self.config.KOTAK_CONSUMER_SECRET,
                environment=self.config.KOTAK_ENVIRONMENT
            )
            
            # Step 1: Login with Mobile and Password
            print("[KotakNeoBroker] Initiating Kotak Neo login...")
            self.client.login(
                mobilenumber=self.config.KOTAK_MOBILE_NUMBER,
                password=self.config.KOTAK_PASSWORD
            )
            
            # Step 2: 2FA Session validation using TOTP
            if self.config.KOTAK_TOTP_KEY:
                totp = pyotp.TOTP(self.config.KOTAK_TOTP_KEY)
                current_otp = totp.now()
                self.client.session_2fa(OTP=current_otp)
                print("[KotakNeoBroker] 2FA TOTP Verified Successfully!")
            elif self.config.KOTAK_MPIN:
                self.client.session_2fa(OTP=self.config.KOTAK_MPIN)
                print("[KotakNeoBroker] 2FA MPIN Verified Successfully!")
                
            self.is_authenticated = True
            print("[KotakNeoBroker] Connected to Kotak Neo Live Account.")
            return True

        except Exception as e:
            print(f"[KotakNeoBroker] Authentication error: {e}")
            self.is_authenticated = False
            return False

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
