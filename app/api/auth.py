import secrets
import httpx
from datetime import datetime, timedelta
from typing import Dict
from fastapi import APIRouter, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from app.db.session import get_db
from app.models import User
from app.schemas.auth import UserResponse, GoogleAuthSuccessResponse, RefreshRequest, RefreshSuccessResponse
from app.services import auth as auth_service
from app.api.deps import get_current_user_from_token
from app.utils.responses import success_response, fail_response
from app.utils.logger import logger
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

# In-memory state store for OAuth CSRF protection
_oauth_states: Dict[str, datetime] = {}


@router.get("/google", summary="Initiate Google OAuth", response_model=GoogleAuthSuccessResponse)
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


@router.get("/google/callback", summary="Google Authentication Callback", include_in_schema=False)
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
        
        # Create refresh token
        refresh_token = await auth_service.create_refresh_token(db=db, user_id=str(user.id))
        
        logger.info(f"Google auth successful for {user.email}")
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Authentication successful",
            data={
                "access_token": jwt_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
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
async def get_current_user_endpoint(current_user: User = Depends(get_current_user_from_token)):
    """Get the currently authenticated user's details."""
    return current_user


@router.post("/refresh", response_model=RefreshSuccessResponse, summary="Refresh Access Token")
async def refresh_access_token(
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a new access token using a valid refresh token.
    
    When to use: Call this endpoint when your access token expires.
    Authentication: None required, but you must provide a valid refresh token in the request body.
    Response: Returns a new access token that you should use for subsequent API calls.
    """
    try:
        # Validate refresh token and get user
        user = await auth_service.validate_refresh_token(db=db, token=refresh_request.refresh_token)
        
        if not user:
            return fail_response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Invalid or expired refresh token"
            )
        
        # Generate new access token
        new_access_token = auth_service.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        
        logger.info(f"Token refreshed for user: {user.email}")
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Token refreshed successfully",
            data={
                "access_token": new_access_token,
                "token_type": "bearer"
            }
        )
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}", exc_info=True)
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Token refresh error: {str(e)}"
        )


@router.post("/logout", summary="Logout (Revoke Refresh Token)")
async def logout(
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke a refresh token (logout).
    
    This invalidates the refresh token so it cannot be used to generate new access tokens.
    The current access token will remain valid until it expires naturally.
    """
    try:
        # Revoke refresh token
        revoked = await auth_service.revoke_refresh_token(db=db, token=refresh_request.refresh_token)
        
        if not revoked:
            return fail_response(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Refresh token not found or already revoked"
            )
        
        logger.info("User logged out successfully")
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Logged out successfully",
            data={"revoked": True}
        )
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}", exc_info=True)
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Logout error: {str(e)}"
        )

