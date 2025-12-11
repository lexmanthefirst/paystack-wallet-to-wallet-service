from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db, engine
from app.core.redis import init_redis, close_redis
from app.api import app as api_router
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - handles startup and shutdown events."""
    # Startup
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    await init_redis()
    logger.info("Database and Redis initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down %s", settings.APP_NAME)
    await engine.dispose()
    await close_redis()
    logger.info("Database and Redis connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Wallet service with Paystack integration and API key authentication",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add correlation ID middleware (for request tracking)
app.add_middleware(CorrelationIdMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Wallet Service API",
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Include API router with prefix
app.include_router(api_router, prefix="/api/v1")

logger.info("Wallet service API routes registered")
