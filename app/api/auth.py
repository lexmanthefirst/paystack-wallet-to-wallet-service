import os
from fastapi import APIRouter, Depends, status, Request, HTTPException
from authlib.integrations.starlette_client import OAuth, OAuthError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.auth import UserResponse
from app.services.auth import create_access_token
from app.api.deps import get_current_user_from_token
from app.config import settings
from app.utils.responses import auth_response, fail_response
from app.utils.logger import logger

# Allow OAuth over HTTP for development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Configure OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'
    }
)


@router.get("/google", summary="Trigger Google Sign-In")
async def google_login(request: Request):
    """
    Triggers Google sign-in.
    Redirects the user to the Google OAuth consent screen.
    """
    # Do not manually clear session here as it might interfere with authlib's state storage
    # request.session.clear() 
    
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    logger.info(f"Initiating Google login with redirect_uri: {redirect_uri}")
    logger.debug(f"Session before redirect: {request.session.keys()}")
    
    try:
        resp = await oauth.google.authorize_redirect(request, redirect_uri)
        logger.debug("Google authorize_redirect called successfully.")
        return resp
    except Exception as e:
        logger.error(f"Failed to create redirect URL: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not initiate Google login")


@router.get("/google/callback", summary="Google Authentication Callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Callback for Google OAuth.
    Logs in the user, creates them if they don't exist, and returns a JWT token.
    """
    logger.debug(f"Callback received. Session keys: {request.session.keys()}")
    try:
        # Exchange code for access token
        token = await oauth.google.authorize_access_token(request)
        
        # Get user info
        user_info = token.get('userinfo')
        if not user_info:
            return fail_response(status.HTTP_400_BAD_REQUEST, "Failed to get user info from Google")
            
        email = user_info.get('email')
        google_id = user_info.get('sub')
        name = user_info.get('name')
        
        if not email or not google_id:
            return fail_response(status.HTTP_400_BAD_REQUEST, "Invalid user info: missing email or ID")
            
        logger.info(f"Google auth successful for {email}")

        # Get or create user (as per spec)
        from app.services.user import get_or_create_user_from_google
        user = await get_or_create_user_from_google(db, email, google_id, name or email.split('@')[0])
        
        # Create JWT token
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        
        # Clear session cookies (we use JWT for auth now)
        request.session.clear()

        # Return Success Response with JWT
        user_data = UserResponse.model_validate(user)
        return auth_response(
            status_code=status.HTTP_200_OK,
            message="Login successful",
            access_token=access_token,
            data={
                "user": {
                    "id": str(user_data.id),
                    "email": user_data.email,
                    "name": user_data.name
                }
            }
        )
        
    except OAuthError as e:
        logger.error(f"OAuth Error: {e.error} {e.description}")
        return fail_response(status.HTTP_400_BAD_REQUEST, f"Authentication failed: {e.description}")
    except Exception as e:
        logger.error(f"Callback error: {str(e)}", exc_info=True)
        return fail_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Authentication failed")


@router.get("/me", response_model=UserResponse, summary="Get Current User")
async def get_current_user_me(
    user: UserResponse = Depends(get_current_user_from_token)
):
    """
    Get the currently authenticated user's profile from the JWT token.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
