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
        description="Descriptive name for the API key (e.g., 'Production Server', 'Mobile App')"
    )
    permissions: List[Literal["deposit", "transfer", "read"]] = Field(
        ...,
        min_items=1,
        description="List of permissions to grant. Available: 'deposit' (initialize deposits), 'transfer' (send funds), 'read' (view balance/history)"
    )
    expiry: Literal["1H", "1D", "1M", "1Y"] = Field(
        ...,
        description="Expiration duration: 1H (1 hour), 1D (1 day), 1M (1 month), 1Y (1 year)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Production API",
                "permissions": ["read", "deposit", "transfer"],
                "expiry": "1M"
            }
        }
    }


class APIKeyResponse(BaseModel):
    """Schema for API key response (only shown once at creation)."""
    api_key: str = Field(
        ...,
        description="The API key - SAVE THIS! It will only be shown once. Format: sk_live_XXXXXXXX..."
    )
    expires_at: datetime = Field(
        ...,
        description="ISO 8601 timestamp when this key expires"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "api_key": "sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
                "expires_at": "2025-12-12T10:00:00.000000"
            }
        }
    }


class APIKeyInfo(BaseModel):
    """Schema for listing API key information (without the actual key)."""
    id: UUID = Field(..., description="Unique identifier for this API key")
    name: str = Field(..., description="Descriptive name of the API key")
    permissions: List[str] = Field(..., description="Granted permissions for this key")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    revoked: bool = Field(..., description="Whether this key has been revoked")
    created_at: datetime = Field(..., description="Timestamp when this key was created")
    is_valid: bool = Field(..., description="Whether this key is currently valid (not revoked and not expired)")
    
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production API",
                "permissions": ["read", "deposit", "transfer"],
                "expires_at": "2025-12-12T10:00:00.000000",
                "revoked": False,
                "created_at": "2025-12-11T10:00:00.000000",
                "is_valid": True
            }
        }
    }


class APIKeyRollover(BaseModel):
    """Schema for rolling over an expired API key."""
    expired_key_id: UUID = Field(
        ...,
        description="ID of the expired API key to rollover. Key must be expired and owned by you."
    )
    expiry: Literal["1H", "1D", "1M", "1Y"] = Field(
        ...,
        description="Expiration duration for the new key: 1H (1 hour), 1D (1 day), 1M (1 month), 1Y (1 year)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "expired_key_id": "550e8400-e29b-41d4-a716-446655440000",
                "expiry": "1M"
            }
        }
    }


class APIKeyRevoke(BaseModel):
    """Schema for revoking an API key."""
    key_id: UUID = Field(
        ...,
        description="ID of the API key to revoke. The key will be immediately invalidated."
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "key_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }


# Response models for Swagger UI
class CreateAPIKeyData(BaseModel):
    """Create API key data."""
    key_id: str
    api_key: str
    expires_at: str
    name: str
    permissions: List[str]
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "key_id": "550e8400-e29b-41d4-a716-446655440000",
                "api_key": "sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
                "expires_at": "2025-12-12T09:00:00.000000",
                "name": "Production API",
                "permissions": ["read", "deposit", "transfer"]
            }
        }
    }


class CreateAPIKeySuccessResponse(BaseModel):
    """Successful create API key response."""
    status: str
    status_code: int
    message: str
    data: CreateAPIKeyData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 201,
                "message": "API key created successfully",
                "data": {
                    "key_id": "550e8400-e29b-41d4-a716-446655440000",
                    "api_key": "sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
                    "expires_at": "2025-12-12T09:00:00.000000",
                    "name": "Production API",
                    "permissions": ["read", "deposit", "transfer"]
                }
            }
        }
    }


class APIKeyListItem(BaseModel):
    """API key list item."""
    id: str
    name: str
    permissions: List[str]
    created_at: str
    expires_at: str
    is_valid: bool


class ListAPIKeysData(BaseModel):
    """List API keys data."""
    keys: List[APIKeyListItem]
    count: int


class ListAPIKeysSuccessResponse(BaseModel):
    """Successful list API keys response."""
    status: str
    status_code: int
    message: str
    data: ListAPIKeysData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Retrieved 2 API key(s)",
                "data": {
                    "keys": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Production API",
                            "permissions": ["read", "deposit", "transfer"],
                            "created_at": "2025-12-11T10:00:00.000000",
                            "expires_at": "2025-12-12T10:00:00.000000",
                            "is_valid": True
                        }
                    ],
                    "count": 2
                }
            }
        }
    }


class RevokeAPIKeySuccessResponse(BaseModel):
    """Successful revoke API key response."""
    status: str
    status_code: int
    message: str
    data: dict
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "API key revoked successfully",
                "data": {}
            }
        }
    }

