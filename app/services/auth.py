import bcrypt
import httpx
from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.user import get_or_create_user_from_google
from app.models import User

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"


def hash_key(key: str) -> str:
    """Hash an API key or password using bcrypt."""
    return bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_key(plain_key: str, hashed_key: str) -> bool:
    """Verify a plain key against its hash."""
    return bcrypt.checkpw(
        plain_key.encode("utf-8"),
        hashed_key.encode("utf-8"),
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def parse_expiry(expiry: str) -> datetime:
    """Parse expiry string (1H, 1D, 1M, 1Y) to datetime."""
    value = int(expiry[:-1])
    unit = expiry[-1].upper()
    now = datetime.utcnow()
    
    if unit == "H":
        return now + timedelta(hours=value)
    elif unit == "D":
        return now + timedelta(days=value)
    elif unit == "M":
        return now + timedelta(days=value * 30)
    elif unit == "Y":
        return now + timedelta(days=value * 365)
    else:
        raise ValueError(f"Invalid expiry format: {expiry}")


async def process_google_oauth_callback(db: AsyncSession, code: str) -> Tuple[User, str]:
    """
    Process Google OAuth callback.
    
    Exchanges authorization code for user info, creates/retrieves user with wallet,
    and generates JWT token.
    """
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        token_response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        access_token = tokens.get("access_token")
        
        if not access_token:
            raise ValueError("Failed to get access token from Google")
        
        headers = {"Authorization": f"Bearer {access_token}"}
        userinfo_response = await client.get(GOOGLE_USERINFO_ENDPOINT, headers=headers)
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()
    
    email = user_info.get("email")
    google_id = user_info.get("id")
    name = user_info.get("name", email)
    
    if not email or not google_id:
        raise ValueError("Failed to get user info from Google")
    
    user = await get_or_create_user_from_google(
        db=db,
        email=email,
        google_id=google_id,
        name=name
    )
    
    jwt_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    return user, jwt_token


async def create_refresh_token(db: AsyncSession, user_id: str) -> str:
    """
    Create a refresh token for a user.
    
    Args:
        db: Database session
        user_id: User ID
        
    Returns:
        Plain refresh token (only shown once)
    """
    from app.models import RefreshToken
    import secrets
    
    # Generate random refresh token
    plain_token = secrets.token_urlsafe(32)
    token_hash = hash_key(plain_token)
    
    # Calculate expiration (30 days)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Create refresh token record
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    
    db.add(refresh_token)
    await db.commit()
    await db.refresh(refresh_token)
    
    return plain_token


async def validate_refresh_token(db: AsyncSession, token: str) -> Optional[User]:
    """
    Validate a refresh token and return the associated user.
    
    Args:
        db: Database session
        token: Plain refresh token
        
    Returns:
        User model if token is valid, None otherwise
    """
    from app.models import RefreshToken
    from sqlalchemy import select
    
    # Get all non-revoked, non-expired tokens
    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.revoked == False)
        .where(RefreshToken.expires_at > datetime.utcnow())
    )
    candidate_tokens = result.scalars().all()
    
    # Verify hash against candidates
    for refresh_token in candidate_tokens:
        if verify_key(token, refresh_token.token_hash):
            # Found matching token, return user
            result = await db.execute(
                select(User).where(User.id == refresh_token.user_id)
            )
            return result.scalar_one_or_none()
    
    return None


async def revoke_refresh_token(db: AsyncSession, token: str) -> bool:
    """
    Revoke a refresh token.
    
    Args:
        db: Database session
        token: Plain refresh token
        
    Returns:
        True if token was revoked, False if not found
    """
    from app.models import RefreshToken
    from sqlalchemy import select
    
    # Get all non-revoked tokens
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.revoked == False)
    )
    candidate_tokens = result.scalars().all()
    
    # Find and revoke matching token
    for refresh_token in candidate_tokens:
        if verify_key(token, refresh_token.token_hash):
            refresh_token.revoked = True
            await db.commit()
            return True
    
    return False

