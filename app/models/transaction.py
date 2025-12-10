import uuid
from decimal import Decimal
from enum import Enum
from sqlalchemy import String, Column, ForeignKey, Numeric, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class TransactionType(str, Enum):
    """Transaction type enumeration."""
    DEPOSIT = "deposit"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


class TransactionStatus(str, Enum):
    """Transaction status enumeration."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Transaction(BaseModel):
    """Transaction model for tracking wallet activities."""
    
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    reference = Column(String, unique=True, nullable=False, index=True)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    meta = Column(JSON, nullable=True)  # Additional data: recipient_wallet, sender_wallet, etc.
    
    # Relationships
    wallet = relationship("Wallet", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction {self.reference} {self.type} {self.amount} {self.status}>"
