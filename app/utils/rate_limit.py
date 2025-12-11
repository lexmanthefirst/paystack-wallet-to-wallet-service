from datetime import timedelta
from functools import wraps
from fastapi import HTTPException, Request, status
from app.core.redis import get_redis
from app.utils.logger import logger


async def check_rate_limit(key: str, max_requests: int, window: timedelta) -> bool:
    """
    Check if request is within rate limit using Fixed Window algorithm.
    
    Returns True if allowed, raises HTTPException if exceeded or Redis unavailable.
    """
    try:
        redis = get_redis()
        
        current = await redis.incr(key)
        
        if current == 1:
            await redis.expire(key, int(window.total_seconds()))
        
        if current > max_requests:
            ttl = await redis.ttl(key)
            logger.warning(f"Rate limit exceeded for {key}: {current}/{max_requests}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
                headers={"Retry-After": str(ttl), "X-RateLimit-Remaining": "0"}
            )
        
        return True
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        # Fail-closed: block request if Redis is down
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is temporarily unavailable, please try again later."
        )


def rate_limit(max_requests: int, window: timedelta):
    """
    Decorator for rate limiting endpoints using Fixed Window algorithm.
    
    Usage:
        @rate_limit(max_requests=5, window=timedelta(minutes=1))
        async def endpoint(request: Request, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request, **kwargs):
            client_ip = request.client.host if request.client else "unknown"
            
            endpoint = f"{request.method}:{request.url.path}"
            key = f"rate_limit:{client_ip}:{endpoint}"
            
            await check_rate_limit(key, max_requests, window)
            
            return await func(*args, request=request, **kwargs)
        
        return wrapper
    return decorator
