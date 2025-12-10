from app.db.base import Base, BaseModel

# Import all models here so Alembic can detect them
from app.models.user import User
from app.models.wallet import Wallet
from app.models.api_key import APIKey
from app.models.transaction import Transaction

__all__ = ["Base", "BaseModel", "User", "Wallet", "APIKey", "Transaction"]
