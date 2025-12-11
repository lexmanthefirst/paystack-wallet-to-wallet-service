import secrets
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import APIKey
from app.schemas.api_key import APIKeyCreate, APIKeyRollover
from app.services.auth import hash_key, parse_expiry
from app.utils.logger import logger


def generate_api_key() -> str:
    """
    Generate a secure random API key.
    
    Returns:
        API key string in format: sk_live_<random_string>
    """
    random_part = secrets.token_urlsafe(32)
    return f"sk_live_{random_part}"


async def create_api_key(
    db: AsyncSession,
    user_id: str,
    key_data: APIKeyCreate
) -> tuple[APIKey, str]:
    """
    Create a new API key for a user.
    
    Args:
        db: Database session
        user_id: User ID
        key_data: API key creation data
        
    Returns:
        Tuple of (APIKey model, plaintext key)
        
    Raises:
        ValueError: If user has 5 or more active keys
    """
    # Check active key count
    result = await db.execute(
        select(func.count(APIKey.id))
        .where(APIKey.user_id == user_id)
        .where(APIKey.revoked == False)
        .where(APIKey.expires_at > datetime.utcnow())
    )
    active_count = result.scalar()
    
    if active_count >= 5:
        logger.warning(f"API key creation failed - user has {active_count} active keys", extra={"user_id": user_id})
        raise ValueError("Maximum of 5 active API keys allowed per user")
    
    logger.info(f"Creating new API key", extra={"user_id": user_id, "key_name": key_data.name})
    
    # Generate and hash key
    plain_key = generate_api_key()
    key_hash = hash_key(plain_key)
    
    # Extract prefix (after sk_live_)
    # Key format: sk_live_<random_part>
    # We use the first 8 chars of the random part as prefix for lookup security
    # plain_key[8:16] gets the first 8 chars of the random part
    key_prefix = plain_key[8:16]
    
    # Parse expiry
    expires_at = parse_expiry(key_data.expiry)
    
    # Create API key
    api_key = APIKey(
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=key_data.name,
        permissions=key_data.permissions,
        expires_at=expires_at
    )
    
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    logger.info(f"API key created successfully", extra={"key_id": str(api_key.id), "expires_at": expires_at.isoformat()})
    
    return api_key, plain_key


async def rollover_api_key(
    db: AsyncSession,
    user_id: str,
    rollover_data: APIKeyRollover
) -> tuple[APIKey, str]:
    """
    Rollover an expired API key with a new one using same permissions.
    
    Args:
        db: Database session
        user_id: User ID
        rollover_data: Rollover request data
        
    Returns:
        Tuple of (new APIKey model, plaintext key)
        
    Raises:
        ValueError: If old key is not found, not expired, or not owned by user
    """
    # Find the expired key
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == rollover_data.expired_key_id)
        .where(APIKey.user_id == user_id)
    )
    old_key = result.scalar_one_or_none()
    
    if not old_key:
        logger.warning(f"API key rollover failed - key not found", extra={"key_id": rollover_data.expired_key_id})
        raise ValueError("API key not found or not owned by user")
    
    if old_key.expires_at > datetime.utcnow():
        logger.warning(f"API key rollover failed - key not expired", extra={"key_id": rollover_data.expired_key_id})
        raise ValueError("API key is not expired yet")
    
    logger.info(f"Rolling over API key", extra={"old_key_id": str(old_key.id), "user_id": user_id})
    
    # Generate new key with same permissions
    plain_key = generate_api_key()
    key_hash = hash_key(plain_key)
    key_prefix = plain_key[8:16]
    expires_at = parse_expiry(rollover_data.expiry)
    
    new_key = APIKey(
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=old_key.name,
        permissions=old_key.permissions,
        expires_at=expires_at
    )
    
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    logger.info(f"API key rolled over successfully", extra={"new_key_id": str(new_key.id)})
    
    return new_key, plain_key


async def revoke_api_key(
    db: AsyncSession,
    user_id: str,
    key_id: str
) -> APIKey:
    """
    Revoke an API key.
    
    Args:
        db: Database session
        user_id: User ID
        key_id: API key ID to revoke
        
    Returns:
        Revoked APIKey model
        
    Raises:
        ValueError: If key not found or not owned by user
    """
    # Find the key
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        logger.warning(f"API key revocation failed - key not found", extra={"key_id": key_id})
        raise ValueError("API key not found or not owned by user")
    
    if api_key.revoked:
        logger.info(f"API key already revoked", extra={"key_id": key_id})
        return api_key
    
    api_key.revoked = True
    await db.commit()
    await db.refresh(api_key)
    
    logger.info(f"API key revoked successfully", extra={"key_id": key_id, "user_id": user_id})
    
    return api_key


async def validate_api_key(
    db: AsyncSession,
    api_key: str
) -> Optional[APIKey]:
    """
    Validate an API key and return the associated APIKey model.
    """
    if not api_key.startswith("sk_live_") or len(api_key) < 16:
        return None
        
    # Extract prefix
    key_prefix = api_key[8:16]
    
    # Lookup by prefix (O(1) operation)
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_prefix == key_prefix)
        .where(APIKey.revoked == False)
        .where(APIKey.expires_at > datetime.utcnow())
    )
    # Theoretically there could be prefix collisions (rare), so we get all matches
    candidate_keys = result.scalars().all()
    
    # Verify hash against candidates
    from app.services.auth import verify_key
    for key_model in candidate_keys:
        if verify_key(api_key, key_model.key_hash):
            return key_model
            
    return None


async def list_user_api_keys(
    db: AsyncSession,
    user_id: str,
    limit: int = 20
) -> list[APIKey]:
    """
    List all API keys for a user with pagination.
    
    Args:
        db: Database session
        user_id: User ID
        limit: Maximum number of keys to return (default: 20)
        
    Returns:
        List of APIKey models ordered by created_at descending
    """
    logger.debug(f"Listing API keys for user: {user_id}", extra={"limit": limit})
    
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc())
        .limit(limit)
    )
    
    keys = list(result.scalars().all())
    
    logger.info(
        f"Retrieved {len(keys)} API keys for user",
        extra={"user_id": user_id, "count": len(keys)}
    )
    
    return keys

