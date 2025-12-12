from datetime import timedelta
from fastapi import APIRouter, Depends, status, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.schemas.api_key import (
    APIKeyCreate, APIKeyRollover, APIKeyRevoke,
    CreateAPIKeySuccessResponse, ListAPIKeysSuccessResponse, RevokeAPIKeySuccessResponse
)
from app.services import api_key as api_key_service
from app.api.deps import get_current_user_from_token
from app.utils.responses import success_response, fail_response
from app.utils.rate_limit import rate_limit
from app.utils.logger import logger

router = APIRouter(prefix="/keys", tags=["API Keys"])


async def require_jwt_auth(current_user: User = Depends(get_current_user_from_token)) -> User:
    """Require JWT authentication for API key management."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required for API key management. Please login with Google OAuth.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=CreateAPIKeySuccessResponse)
@rate_limit(max_requests=3, window=timedelta(hours=1))
async def create_api_key(
    request: Request,
    key_data: APIKeyCreate,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """Create new API key. Max 5 active keys per user."""
    try:
        api_key, plain_key = await api_key_service.create_api_key(
            db=db, user_id=str(current_user.id), key_data=key_data
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
        })
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"API key creation failed: {str(e)}", exc_info=True)
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create API key: {str(e)}"
        )




@router.post("/rollover", response_model=CreateAPIKeySuccessResponse)
async def rollover_api_key(
    rollover_data: APIKeyRollover,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """Rollover expired API key with new one using same permissions."""
    try:
        api_key, plain_key = await api_key_service.rollover_api_key(
            db=db, user_id=str(current_user.id), rollover_data=rollover_data
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
        })
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(e)
        )


@router.get("", response_model=ListAPIKeysSuccessResponse)
async def list_api_keys(
    limit: int = 20,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """List all API keys for authenticated user (max 20)."""
    api_keys = await api_key_service.list_user_api_keys(db=db, user_id=str(current_user.id), limit=limit)
    
    keys_data = [{
        "id": str(key.id),
        "name": key.name,
        "permissions": key.permissions,
        "created_at": key.created_at.isoformat(),
        "expires_at": key.expires_at.isoformat(),
        "is_valid": key.is_valid()
    } for key in api_keys]
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message=f"Retrieved {len(keys_data)} API key(s)",
        data={
        "keys": keys_data, 
        "count": len(keys_data)
    })




@router.post("/revoke", response_model=RevokeAPIKeySuccessResponse)
async def revoke_api_key(
    revoke_data: APIKeyRevoke,
    current_user: User = Depends(require_jwt_auth),
    db: AsyncSession = Depends(get_db)
):
    """Revoke API key immediately."""
    try:
        await api_key_service.revoke_api_key(
            db=db, user_id=str(current_user.id), key_id=str(revoke_data.key_id)
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

