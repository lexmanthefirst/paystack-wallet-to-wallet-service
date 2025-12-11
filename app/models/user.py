import uuid
from sqlalchemy import String, Column
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class User(BaseModel):
    """User model for Google OAuth authentication."""
    
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    google_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    
    # Relationships
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"

