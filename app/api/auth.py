import secrets
import httpx
from datetime import datetime, timedelta
from typing import Dict
from fastapi import APIRouter, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from app.db.session import get_db
from app.models import User
from app.schemas.auth import UserResponse
from app.services import auth as auth_service
from app.api.deps import get_current_user_from_token
from app.utils.responses import success_response, fail_response
from app.utils.logger import logger
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

# In-memory state store for OAuth CSRF protection
_oauth_states: Dict[str, datetime] = {}


@router.get("/google", summary="Initiate Google OAuth")
async def google_login():
    """Get Google OAuth authorization URL."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.utcnow()
    
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    authorization_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
    
    logger.info(f"Initiating Google login with redirect_uri: {settings.GOOGLE_REDIRECT_URI}")
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Google OAuth URL generated",
        data={"authorization_url": authorization_url}
    )


@router.get("/google/callback", summary="Google Authentication Callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback and return JWT token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code:
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Authorization code not found"
        )
    
    if not state:
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="State parameter not found"
        )
    
    if state not in _oauth_states:
        logger.warning(f"Invalid OAuth state received: {state[:10]}...")
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid or expired state parameter. Please try logging in again."
        )
    
    state_age = datetime.utcnow() - _oauth_states[state]
    if state_age > timedelta(minutes=5):
        del _oauth_states[state]
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="State parameter expired. Please try logging in again."
        )
    
    del _oauth_states[state]
    
    try:
        user, jwt_token = await auth_service.process_google_oauth_callback(db=db, code=code)
        
        logger.info(f"Google auth successful for {user.email}")
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Authentication successful",
            data={
                "jwt_token": jwt_token,
                "user": {
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email
                }
            }
        )
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Google OAuth HTTP error: {e.response.status_code} - {e.response.text}")
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Google authentication failed: {str(e)}"
        )
    except ValueError as e:
        logger.error(f"Google OAuth validation error: {str(e)}")
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}", exc_info=True)
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Authentication error: {str(e)}"
        )


@router.get("/me", response_model=UserResponse, summary="Get Current User")
async def get_current_user(current_user: User = Depends(get_current_user_from_token)):
    """Get the currently authenticated user's details."""
    return current_user
