import aioredis
import os
import logging
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
REDIS_RETRY_ON_TIMEOUT = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
REDIS_HEALTH_CHECK_INTERVAL = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))

# Global Redis connection pool
_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None

async def init_redis_pool():
    """Initialize Redis connection pool"""
    global _redis_pool, _redis_client
    
    try:
        _redis_pool = aioredis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=REDIS_MAX_CONNECTIONS,
            retry_on_timeout=REDIS_RETRY_ON_TIMEOUT,
            health_check_interval=REDIS_HEALTH_CHECK_INTERVAL
        )
        
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)
        
        # Test connection
        await _redis_client.ping()
        logger.info(f"Redis connection pool initialized: {REDIS_URL}")
        
    except Exception as e:
        logger.error(f"Failed to initialize Redis pool: {e}")
        raise

async def get_redis() -> aioredis.Redis:
    """Get Redis client with connection pooling"""
    if _redis_client is None:
        await init_redis_pool()
    
    return _redis_client

async def close_redis_pool():
    """Close Redis connection pool"""
    global _redis_pool, _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
    
    logger.info("Redis connection pool closed")

@asynccontextmanager
async def redis_transaction():
    """Context manager for Redis transactions"""
    redis = await get_redis()
    pipe = redis.pipeline()
    try:
        yield pipe
        await pipe.execute()
    except Exception as e:
        logger.error(f"Redis transaction failed: {e}")
        raise
    finally:
        await pipe.reset()

async def health_check() -> bool:
    """Check Redis health"""
    try:
        redis = await get_redis()
        await redis.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False

# Utility functions for common Redis operations
async def set_with_expiry(key: str, value: str, expiry_seconds: int = 3600):
    """Set key with expiry"""
    redis = await get_redis()
    await redis.setex(key, expiry_seconds, value)

async def get_or_default(key: str, default: str = None):
    """Get key or return default"""
    redis = await get_redis()
    result = await redis.get(key)
    return result.decode() if result else default

async def delete_pattern(pattern: str) -> int:
    """Delete keys matching pattern"""
    redis = await get_redis()
    keys = []
    async for key in redis.scan_iter(match=pattern):
        keys.append(key)
    
    if keys:
        return await redis.delete(*keys)
    return 0
