from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models import User
from app.schemas.api_key import APIKeyCreate, APIKeyRollover, APIKeyRevoke, APIKeyResponse
from app.services import api_key as api_key_service
from app.api.deps import get_current_user, get_current_user_from_token
from app.utils.responses import success_response, fail_response


router = APIRouter(prefix="/keys", tags=["API Keys"])


async def require_jwt_auth(
    current_user: User = Depends(get_current_user_from_token),
) -> User:
    """
    Require JWT authentication.
    
    This is used for API key management endpoints to prevent
    privilege escalation attacks.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required for API key management. Please login with Google OAuth.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    summary="Create API Key",
    description="""
    Create a new API key for the authenticated user.
    
    **Important Notes:**
    - Maximum 5 active keys per user
    - The API key is only shown ONCE - save it immediately!
    - Keys cannot be retrieved after creation
    - Use appropriate permissions for your use case
    
    **Permissions:**
    - `read`: View wallet balance and transaction history
    - `deposit`: Initialize deposit transactions (requires Paystack)
    - `transfer`: Send funds to other wallets
    
    **Expiry Options:**
    - `1H`: 1 hour (testing/development)
    - `1D`: 1 day (short-lived)
    - `1M`: 1 month (recommended for production)
    - `1Y`: 1 year (long-lived, use with caution)
    
    **Authentication:** Requires JWT token (Google OAuth) - API keys cannot create other API keys
    """,
    responses={
        201: {
            "description": "API key created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "API key created successfully",
                        "data": {
                            "api_key": "sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
                            "expires_at": "2025-12-10T14:52:11.000Z",
                            "name": "Production API",
                            "permissions": ["read", "deposit", "transfer"]
                        }
                    }
                }
            }
        },
        400: {
            "description": "Maximum key limit reached (5 active keys)",
            "content": {
                "application/json": {
                    "example": {
                        "status": "fail",
                        "message": "Maximum of 5 active API keys allowed per user"
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed - JWT token required (API keys cannot manage other API keys)"
        }
    }
)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key for the authenticated user.
    
    Maximum 5 active keys per user.
    Requires JWT authentication - API keys cannot create other API keys.
    """
    try:
        api_key, plain_key = await api_key_service.create_api_key(
            db=db,
            user_id=str(current_user.id),
            key_data=key_data
        )
        
        return success_response(
            status_code=status.HTTP_201_CREATED,
            message="API key created successfully",
            data={
                "key_id": str(api_key.id),
                "api_key": plain_key,
                "expires_at": api_key.expires_at.isoformat(),
                "name": api_key.name,
                "permissions": api_key.permissions
            }
        )
        
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )
    except Exception as e:
        # Log unexpected errors for debugging
        import logging
        logging.error(f"API key creation failed: {str(e)}", exc_info=True)
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create API key: {str(e)}"
        )


@router.post(
    "/rollover",
    response_model=None,
    summary="Rollover Expired API Key",
    description="""
    Rollover an expired API key with a new one using the same permissions.
    
    **Use Case:** When your API key expires, use this endpoint to generate a new key 
    without needing to update your permission configuration.
    
    **Requirements:**
    - The old key must be expired
    - The old key must be owned by the authenticated user
    - The old key ID can be found from the key creation response or listing endpoint
    
    **Authentication:** Requires JWT token (Google OAuth) - API keys cannot rollover other API keys
    """,
    responses={
        200: {
            "description": "API key rolled over successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "API key rolled over successfully",
                        "data": {
                            "api_key": "sk_live_NewKeyHereXXXXXXXXXXXXXXXXXXXXXXXX",
                            "expires_at": "2026-01-09T14:52:11.000Z",
                            "name": "Production API",
                            "permissions": ["read", "deposit", "transfer"]
                        }
                    }
                }
            }
        },
        404: {
            "description": "API key not found or not expired",
            "content": {
                "application/json": {
                    "example": {
                        "status": "fail",
                        "message": "API key not found or not owned by user"
                    }
                }
            }
        }
    }
)
async def rollover_api_key(
    rollover_data: APIKeyRollover,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """
    Rollover an expired API key with a new one using the same permissions.
    Requires JWT authentication - API keys cannot rollover other API keys.
    """
    try:
        api_key, plain_key = await api_key_service.rollover_api_key(
            db=db,
            user_id=str(current_user.id),
            rollover_data=rollover_data
        )
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="API key rolled over successfully",
            data={
                "key_id": str(api_key.id),
                "api_key": plain_key,
                "expires_at": api_key.expires_at.isoformat(),
                "name": api_key.name,
                "permissions": api_key.permissions
            }
        )
        
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(e)
        )


@router.post(
    "/revoke",
    response_model=None,
    summary="Revoke API Key",
    description="""
    Immediately revoke an API key, making it unusable for future requests.
    
    **Use Cases:**
    - Key has been compromised or leaked
    - Decommissioning an application
    - Security best practice: revoke unused keys
    
    **Effect:** The key will be immediately invalidated and cannot be used for authentication.
    Any requests using this key will receive a 401 Unauthorized response.
    
    **Note:** This action cannot be undone. You'll need to create a new key if needed.
    
    **Authentication:** Requires JWT token (Google OAuth) - API keys cannot revoke other API keys
    """,
    responses={
        200: {
            "description": "API key revoked successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "API key revoked successfully"
                    }
                }
            }
        },
        404: {
            "description": "API key not found or not owned by user",
            "content": {
                "application/json": {
                    "example": {
                        "status": "fail",
                        "message": "API key not found or not owned by user"
                    }
                }
            }
        }
    }
)
async def revoke_api_key(
    revoke_data: APIKeyRevoke,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke an API key.
    Requires JWT authentication - API keys cannot revoke other API keys.
    """
    try:
        await api_key_service.revoke_api_key(
            db=db,
            user_id=str(current_user.id),
            key_id=str(revoke_data.key_id)
        )
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="API key revoked successfully"
        )
        
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(e)
        )
