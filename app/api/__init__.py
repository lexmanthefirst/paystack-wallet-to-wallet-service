from fastapi import APIRouter

from .auth import router as auth_router
from .api_keys import router as api_keys_router
from .wallet import router as wallet_router


app = APIRouter()

app.include_router(auth_router)

app.include_router(api_keys_router)

app.include_router(wallet_router)
