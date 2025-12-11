import uuid
from datetime import datetime
from sqlalchemy import String, Column, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class RefreshToken(BaseModel):
    """Refresh token model for token-based authentication."""
    
    __tablename__ = "refresh_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="refresh_tokens")
    
    def is_valid(self) -> bool:
        """Check if refresh token is valid (not expired and not revoked)."""
        return not self.revoked and datetime.utcnow() < self.expires_at
    
    def __repr__(self):
        return f"<RefreshToken {self.id} user={self.user_id} valid={self.is_valid()}>"
