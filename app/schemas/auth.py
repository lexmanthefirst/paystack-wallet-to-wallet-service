from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    name: str


class UserCreate(UserBase):
    """Schema for creating a user."""
    google_id: str


class UserResponse(UserBase):
    """Schema for user response."""
    id: UUID
    google_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "refresh_token": "xYz123AbC_-456DeF789GhI..."
            }
        }
    }


class RefreshTokenData(BaseModel):
    """Refresh token response data."""
    access_token: str
    token_type: str = "bearer"
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
    }


class RefreshSuccessResponse(BaseModel):
    """Successful refresh response."""
    status: str
    status_code: int
    message: str
    data: RefreshTokenData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Token refreshed successfully",
                "data": {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer"
                }
            }
        }
    }


# Response models for Swagger UI
class GoogleAuthData(BaseModel):
    """Google OAuth URL data."""
    authorization_url: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=..."
            }
        }
    }


class GoogleAuthSuccessResponse(BaseModel):
    """Successful Google OAuth response."""
    status: str
    status_code: int
    message: str
    data: GoogleAuthData
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "status_code": 200,
                "message": "Google OAuth URL generated",
                "data": {
                    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=..."
                }
            }
        }
    }


