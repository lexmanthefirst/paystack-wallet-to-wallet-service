from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Wallet, Transaction, TransactionType, TransactionStatus, User
from app.utils.logger import logger


async def get_user_wallet(
    db: AsyncSession, 
    user_id: str,
    for_update: bool = False
) -> Optional[Wallet]:
    """Get user's wallet with optional row locking."""
    logger.debug(f"Fetching wallet for user: {user_id} (lock={for_update})")
    query = select(Wallet).where(Wallet.user_id == user_id)
    
    if for_update:
        query = query.with_for_update()
        
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_wallet_by_number(
    db: AsyncSession, 
    wallet_number: str,
    for_update: bool = False
) -> Optional[Wallet]:
    """Get wallet by wallet number with optional row locking."""
    query = select(Wallet).where(Wallet.wallet_number == wallet_number)
    
    if for_update:
        query = query.with_for_update()
        
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def credit_wallet(
    db: AsyncSession,
    wallet: Wallet,
    amount: Decimal,
    transaction: Transaction
) -> Wallet:
    """Credit wallet and update transaction status."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    logger.info(f"Crediting {wallet.wallet_number}: {amount}, ref: {transaction.reference}")
    
    wallet.balance += amount
    transaction.status = TransactionStatus.SUCCESS
    
    await db.commit()
    await db.refresh(wallet)
    await db.refresh(transaction)
    
    logger.info(f"Wallet credited: {wallet.wallet_number}, balance: {wallet.balance}")
    
    return wallet


async def transfer_funds(
    db: AsyncSession,
    sender_wallet_number: str,
    recipient_wallet_number: str,
    amount: Decimal
) -> tuple[Transaction, Transaction]:
    """Transfer funds atomically with deadlock prevention via ordered locking."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    logger.info(f"Transfer: {sender_wallet_number} → {recipient_wallet_number}, {amount}")
    
    # Deadlock Prevention: Always acquire locks in consistent order (lexical)
    # This prevents Wallet A→B waiting for Wallet B→A
    first_wallet_num, second_wallet_num = sorted([sender_wallet_number, recipient_wallet_number])
    
    w1 = await get_wallet_by_number(db, first_wallet_num, for_update=True)
    w2 = await get_wallet_by_number(db, second_wallet_num, for_update=True)
    
    if not w1 or not w2:
        raise ValueError("One or both wallets not found")
    
    sender_wallet = w1 if w1.wallet_number == sender_wallet_number else w2
    recipient_wallet = w2 if w2.wallet_number == recipient_wallet_number else w1
    
    if sender_wallet.balance < amount:
        logger.warning(f"Insufficient balance: {sender_wallet.balance} < {amount}")
        raise ValueError("Insufficient balance")
    
    import uuid
    reference = f"TRF_{uuid.uuid4().hex[:12].upper()}"
    
    
    sender_txn = Transaction(
        wallet_id=sender_wallet.id, type=TransactionType.TRANSFER_OUT,
        amount=amount, reference=f"{reference}_OUT",
        status=TransactionStatus.PENDING,
        meta={"recipient_wallet": recipient_wallet.wallet_number}
    )
    
    recipient_txn = Transaction(
        wallet_id=recipient_wallet.id, type=TransactionType.TRANSFER_IN,
        amount=amount, reference=f"{reference}_IN",
        status=TransactionStatus.PENDING,
        meta={"sender_wallet": sender_wallet.wallet_number}
    )
    
    try:
        sender_wallet.balance -= amount
        sender_txn.status = TransactionStatus.SUCCESS
        
        recipient_wallet.balance += amount
        recipient_txn.status = TransactionStatus.SUCCESS
        
        db.add(sender_txn)
        db.add(recipient_txn)
        
        await db.commit()
        await db.refresh(sender_txn)
        await db.refresh(recipient_txn)
        
        logger.info(f"Transfer complete: {reference}, {amount} from {sender_wallet.wallet_number} → {recipient_wallet.wallet_number}")
        
        return sender_txn, recipient_txn
        
    except Exception as e:
        await db.rollback()
        sender_txn.status = TransactionStatus.FAILED
        recipient_txn.status = TransactionStatus.FAILED
        logger.error(f"Transfer failed: {reference}, {str(e)}", exc_info=True)
        raise e


async def get_wallet_transactions(
    db: AsyncSession,
    wallet_id: str,
    limit: int = 50
) -> list[Transaction]:
    """Get transaction history for wallet (default 50)."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.wallet_id == wallet_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
