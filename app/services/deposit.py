import uuid
from decimal import Decimal
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Wallet
from app.services import transaction as transaction_service
from app.services.paystack import paystack_service
from app.utils.logger import logger


async def initialize_deposit(
    db: AsyncSession,
    wallet: Wallet,
    amount: Decimal,
    user_email: str
) -> Dict:
    """
    Initialize a Paystack deposit transaction.
    
    Args:
        db: Database session
        wallet: User's wallet
        amount: Amount to deposit
        user_email: User's email for Paystack
        
    Returns:
        Dict with reference and authorization_url
        
    Raises:
        Exception: If Paystack initialization fails
    """
    # Generate unique reference
    reference = f"DEP_{uuid.uuid4().hex[:12].upper()}"
    
    logger.info(
        f"Initializing deposit for wallet: {wallet.wallet_number}",
        extra={"amount": str(amount), "reference": reference}
    )
    
    # Create pending transaction
    await transaction_service.create_pending_transaction(
        db=db,
        wallet_id=str(wallet.id),
        amount=amount,
        reference=reference
    )
    
    # Initialize Paystack transaction
    paystack_data = await paystack_service.initialize_transaction(
        email=user_email,
        amount=amount,
        reference=reference
    )
    
    logger.info(
        f"Deposit initialized successfully",
        extra={"reference": reference, "authorization_url": paystack_data["authorization_url"]}
    )
    
    return {
        "reference": reference,
        "authorization_url": paystack_data["authorization_url"]
    }
