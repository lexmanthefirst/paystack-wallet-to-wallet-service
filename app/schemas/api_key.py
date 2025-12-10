from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import List, Literal


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Descriptive name for the API key (e.g., 'Production Server', 'Mobile App')",
        examples=["Production API", "Development Server", "Mobile App Integration"]
    )
    permissions: List[Literal["deposit", "transfer", "read"]] = Field(
        ...,
        min_items=1,
        description="List of permissions to grant. Available: 'deposit' (initialize deposits), 'transfer' (send funds), 'read' (view balance/history)",
        examples=[["read", "deposit"], ["read", "deposit", "transfer"]]
    )
    expiry: Literal["1H", "1D", "1M", "1Y"] = Field(
        ...,
        description="Expiration duration: 1H (1 hour), 1D (1 day), 1M (1 month), 1Y (1 year)",
        examples=["1D", "1M"]
    )


class APIKeyResponse(BaseModel):
    """Schema for API key response (only shown once at creation)."""
    api_key: str = Field(
        ...,
        description="The API key - SAVE THIS! It will only be shown once. Format: sk_live_XXXXXXXX...",
        examples=["sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"]
    )
    expires_at: datetime = Field(
        ...,
        description="ISO 8601 timestamp when this key expires",
        examples=["2025-12-10T14:52:11.000Z"]
    )


class APIKeyInfo(BaseModel):
    """Schema for listing API key information (without the actual key)."""
    id: UUID = Field(
        ...,
        description="Unique identifier for this API key",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    name: str = Field(
        ...,
        description="Descriptive name of the API key",
        examples=["Production API"]
    )
    permissions: List[str] = Field(
        ...,
        description="Granted permissions for this key",
        examples=[["read", "deposit", "transfer"]]
    )
    expires_at: datetime = Field(
        ...,
        description="Expiration timestamp",
        examples=["2025-12-10T14:52:11.000Z"]
    )
    revoked: bool = Field(
        ...,
        description="Whether this key has been revoked",
        examples=[False]
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when this key was created",
        examples=["2025-12-09T14:52:11.000Z"]
    )
    
    class Config:
        from_attributes = True


class APIKeyRollover(BaseModel):
    """Schema for rolling over an expired API key."""
    expired_key_id: UUID = Field(
        ...,
        description="ID of the expired API key to rollover. Key must be expired and owned by you.",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    expiry: Literal["1H", "1D", "1M", "1Y"] = Field(
        ...,
        description="Expiration duration for the new key: 1H (1 hour), 1D (1 day), 1M (1 month), 1Y (1 year)",
        examples=["1D"]
    )


class APIKeyRevoke(BaseModel):
    """Schema for revoking an API key."""
    key_id: UUID = Field(
        ...,
        description="ID of the API key to revoke. The key will be immediately invalidated.",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
