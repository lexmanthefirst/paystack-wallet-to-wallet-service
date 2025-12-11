from redis.asyncio import Redis
from typing import Optional
from app.config import settings
from app.utils.logger import logger

redis_client: Optional[Redis] = None


async def init_redis():
    """Initialize Redis connection for rate limiting and caching."""
    global redis_client
    
    if not settings.REDIS_ENABLED:
        logger.warning("Redis is disabled, rate limiting will not work")
        return
    
    try:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=10,
            socket_connect_timeout=5
        )
        await redis_client.ping()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None


async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


def get_redis() -> Redis:
    """Get Redis client instance."""
    if not redis_client:
        raise RuntimeError("Redis not initialized. Check REDIS_URL and REDIS_ENABLED settings.")
    return redis_client
