from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from typing import List


class WalletResponse(BaseModel):
    """Schema for wallet response."""
    id: UUID
    wallet_number: str
    balance: Decimal
    created_at: datetime
    
    class Config:
        from_attributes = True


class BalanceResponse(BaseModel):
    """Schema for balance response."""
    balance: Decimal


class DepositRequest(BaseModel):
    """Schema for deposit request."""
    amount: Decimal = Field(..., gt=0, description="Amount to deposit (must be positive)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "amount": 5000.00
            }
        }
    }


class DepositResponse(BaseModel):
    """Schema for deposit response."""
    reference: str
    authorization_url: str


class TransferRequest(BaseModel):
    """Schema for wallet transfer request."""
    wallet_number: str = Field(..., min_length=13, max_length=13, description="Recipient's 13-digit wallet number")
    amount: Decimal = Field(..., gt=0, description="Amount to transfer (must be positive)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "wallet_number": "1234567890123",
                "amount": 1000.00
            }
        }
    }


class TransferResponse(BaseModel):
    """Schema for transfer response."""
    status: str
    message: str


# Response models for Swagger UI
class BalanceData(BaseModel):
    """Balance data."""
    wallet_number: str
    balance: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "wallet_number": "1234567890123",
                "balance": "5000.00"
            }
        }
    }


class BalanceSuccessResponse(BaseModel):
    """Successful balance response."""
    status: str
    status_code: int
    message: str
    data: BalanceData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Balance retrieved successfully",
                "data": {
                    "wallet_number": "1234567890123",
                    "balance": "5000.00"
                }
            }
        }
    }


class DepositData(BaseModel):
    """Deposit initialization data."""
    reference: str
    authorization_url: str
    amount: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "reference": "DEP_ABC123XYZ",
                "authorization_url": "https://checkout.paystack.com/xyz",
                "amount": "5000.00"
            }
        }
    }


class DepositSuccessResponse(BaseModel):
    """Successful deposit response."""
    status: str
    status_code: int
    message: str
    data: DepositData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Deposit initialized successfully",
                "data": {
                    "reference": "DEP_ABC123XYZ",
                    "authorization_url": "https://checkout.paystack.com/xyz",
                    "amount": "5000.00"
                }
            }
        }
    }


class TransferData(BaseModel):
    """Transfer data."""
    status: str
    amount: str
    recipient_wallet: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "amount": "1000.00",
                "recipient_wallet": "1234567890123"
            }
        }
    }


class TransferSuccessResponse(BaseModel):
    """Successful transfer response."""
    status: str
    status_code: int
    message: str
    data: TransferData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Transfer completed successfully",
                "data": {
                    "status": "success",
                    "amount": "1000.00",
                    "recipient_wallet": "1234567890123"
                }
            }
        }
    }


class TransactionItem(BaseModel):
    """Transaction item."""
    id: str
    type: str
    amount: str
    reference: str
    status: str
    created_at: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "type": "DEPOSIT",
                "amount": "5000.00",
                "reference": "DEP_ABC123XYZ",
                "status": "SUCCESS",
                "created_at": "2025-12-11T09:10:30.275Z"
            }
        }
    }


class TransactionsData(BaseModel):
    """Transactions data."""
    transactions: List[TransactionItem]
    count: int


class TransactionsSuccessResponse(BaseModel):
    """Successful transactions response."""
    status: str
    status_code: int
    message: str
    data: TransactionsData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Transaction history retrieved successfully",
                "data": {
                    "transactions": [
                        {
                            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "type": "DEPOSIT",
                            "amount": "5000.00",
                            "reference": "DEP_ABC123XYZ",
                            "status": "SUCCESS",
                            "created_at": "2025-12-11T09:10:30.275Z"
                        }
                    ],
                    "count": 1
                }
            }
        }
    }

