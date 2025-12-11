from typing import Optional, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Transaction, TransactionStatus, Wallet
from app.services import wallet as wallet_service
from app.services import transaction as transaction_service
from app.utils.logger import logger


async def process_successful_charge(
    db: AsyncSession,
    reference: str
) -> Dict:
    """
    Process a successful charge event from Paystack webhook.
    
    Args:
        db: Database session
        reference: Transaction reference from Paystack
        
    Returns:
        Dict with processing status
    """
    logger.info(f"Processing successful charge webhook: {reference}")
    
    # Get transaction
    transaction = await transaction_service.get_transaction_by_reference(db, reference)
    
    if not transaction:
        # Transaction not found, possibly not from our system
        logger.warning(f"Transaction not found for reference: {reference}")
        return {"status": True, "message": "Transaction not found"}
    
    # Check if already processed
    if transaction.status == TransactionStatus.SUCCESS:
        logger.info(f"Transaction already processed: {reference}")
        return {"status": True, "message": "Transaction already processed"}
    
    result = await db.execute(
        select(Wallet).where(Wallet.id == transaction.wallet_id).with_for_update()
    )
    wallet = result.scalar_one_or_none()
    
    if not wallet:
        logger.error(f"Wallet not found for transaction: {reference}")
        raise ValueError("Wallet not found for transaction")
    
    # Credit wallet
    await wallet_service.credit_wallet(
        db=db,
        wallet=wallet,
        amount=transaction.amount,
        transaction=transaction
    )
    
    logger.info(
        f"Charge processed successfully: {reference}",
        extra={"amount": str(transaction.amount), "wallet": wallet.wallet_number}
    )
    
    return {"status": True, "message": "Wallet credited successfully"}


async def process_failed_charge(
    db: AsyncSession,
    reference: str
) -> Dict:
    """
    Process a failed charge event from Paystack webhook.
    
    Args:
        db: Database session
        reference: Transaction reference from Paystack
        
    Returns:
        Dict with processing status
    """
    logger.info(f"Processing failed charge webhook: {reference}")
    
    # Get transaction
    transaction = await transaction_service.get_transaction_by_reference(db, reference)
    
    if not transaction:
        # Transaction not found, possibly not from our system
        logger.warning(f"Transaction not found for reference: {reference}")
        return {"status": True, "message": "Transaction not found"}
    
    # Check if already marked as failed
    if transaction.status == TransactionStatus.FAILED:
        logger.info(f"Transaction already marked as failed: {reference}")
        return {"status": True, "message": "Transaction already marked as failed"}
    
    # Check if already successful (shouldn't happen, but safety check)
    if transaction.status == TransactionStatus.SUCCESS:
        logger.warning(f"Cannot mark successful transaction as failed: {reference}")
        return {"status": False, "message": "Transaction already successful"}
    
    # Mark transaction as failed
    transaction.status = TransactionStatus.FAILED
    await db.commit()
    await db.refresh(transaction)
    
    logger.info(
        f"Transaction marked as failed: {reference}",
        extra={"amount": str(transaction.amount), "wallet_id": str(transaction.wallet_id)}
    )
    
    return {"status": True, "message": "Transaction marked as failed"}

