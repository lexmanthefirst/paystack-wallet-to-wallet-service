import httpx
import hashlib
import hmac
from typing import Optional
from decimal import Decimal
from app.config import settings
from app.utils.logger import logger


class PaystackService:
    """Service for interacting with Paystack API."""
    
    BASE_URL = "https://api.paystack.co"
    
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    async def initialize_transaction(
        self,
        email: str,
        amount: Decimal,
        reference: str
    ) -> dict:
        """
        Initialize a Paystack transaction.
        
        Args:
            email: User's email
            amount: Amount in naira (will be converted to kobo)
            reference: Unique transaction reference
            
        Returns:
            Dict containing authorization_url and other transaction data
        """
        # Convert amount to kobo (smallest currency unit)
        amount_kobo = int(amount * 100)
        
        logger.info(
            f"Initializing Paystack transaction",
            extra={"email": email, "amount_naira": str(amount), "reference": reference}
        )
        
        payload = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "callback_url": f"{settings.APP_BASE_URL}/api/v1/wallet/payment/callback"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/transaction/initialize",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            if data["status"]:
                logger.info(f"Paystack transaction initialized: {reference}")
                return data["data"]
            else:
                logger.error(f"Paystack initialization failed: {data.get('message')}")
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")
    
    async def verify_transaction(self, reference: str) -> dict:
        """
        Verify a transaction with Paystack.
        
        Args:
            reference: Transaction reference
            
        Returns:
            Transaction data from Paystack
        """
        logger.debug(f"Verifying Paystack transaction: {reference}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/transaction/verify/{reference}",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            if data["status"]:
                logger.info(f"Paystack transaction verified: {reference}")
                return data["data"]
            else:
                logger.error(f"Paystack verification failed: {data.get('message')}")
                raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")
    
    @staticmethod
    def validate_webhook_signature(body: bytes, signature: str) -> bool:
        """
        Validate Paystack webhook signature.
        
        Args:
            body: Request body as bytes
            signature: Signature from x-paystack-signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        computed_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            body,
            hashlib.sha512
        ).hexdigest()
        
        is_valid = hmac.compare_digest(computed_signature, signature)
        
        if not is_valid:
            logger.warning("Invalid Paystack webhook signature")
        
        return is_valid


# Singleton instance
paystack_service = PaystackService()
