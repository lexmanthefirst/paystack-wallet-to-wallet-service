from typing import Optional, List
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models import User, APIKey
from app.services.auth import decode_access_token
from app.services.api_key import validate_api_key


security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Get current user from JWT token.
    
    Args:
        credentials: HTTP Authorization credentials
        db: Database session
        
    Returns:
        User model or None
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    return user


async def get_current_user_from_api_key(
    x_api_key: Optional[str] = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> tuple[Optional[User], Optional[APIKey]]:
    """
    Get current user from API key.
    
    Args:
        x_api_key: API key from header (X-API-Key)
        db: Database session
        
    Returns:
        Tuple of (User model or None, APIKey model or None)
    """
    if not x_api_key:
        return None, None
    
    api_key = await validate_api_key(db, x_api_key)
    
    if not api_key:
        return None, None
    
    result = await db.execute(
        select(User).where(User.id == api_key.user_id)
    )
    user = result.scalar_one_or_none()
    
    return user, api_key


async def get_current_user(
    user_from_token: Optional[User] = Depends(get_current_user_from_token),
    user_and_key_from_api: tuple = Depends(get_current_user_from_api_key),
) -> User:
    """
    Get current user from either JWT token or API key.
    
    Args:
        user_from_token: User from JWT token
        user_and_key_from_api: Tuple of (User, APIKey) from API key
        
    Returns:
        User model
        
    Raises:
        HTTPException: If no valid authentication provided
    """
    user_from_api_key, _ = user_and_key_from_api
    
    user = user_from_token or user_from_api_key
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_user_with_key(
    user_from_token: Optional[User] = Depends(get_current_user_from_token),
    user_and_key_from_api: tuple = Depends(get_current_user_from_api_key),
) -> tuple[User, Optional[APIKey]]:
    """
    Get current user and API key (if using API key auth).
    
    Args:
        user_from_token: User from JWT token
        user_and_key_from_api: Tuple of (User, APIKey) from API key
        
    Returns:
        Tuple of (User model, APIKey model or None)
        
    Raises:
        HTTPException: If no valid authentication provided
    """
    user_from_api_key, api_key = user_and_key_from_api
    
    user = user_from_token or user_from_api_key
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user, api_key


def require_permissions(required_permissions: List[str]):
    """
    Dependency factory to check API key permissions.
    
    Args:
        required_permissions: List of required permissions
        
    Returns:
        Dependency function
    """
    async def permission_checker(
        user_and_key: tuple = Depends(get_current_user_with_key)
    ) -> User:
        user, api_key = user_and_key
        
        # If using JWT, allow all permissions
        if not api_key:
            return user
        
        # Check API key permissions
        for permission in required_permissions:
            if permission not in api_key.permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key missing required permission: {permission}"
                )
        
        return user
    
    return permission_checker
