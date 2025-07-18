import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque
import redis.asyncio as redis

class RateLimiter:
    """Redis-backed rate limiter with sliding window"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.local_cache: Dict[str, deque] = defaultdict(lambda: deque())
    
    async def is_allowed(self, 
                        key: str, 
                        limit: int, 
                        window_seconds: int,
                        use_redis: bool = True) -> tuple[bool, Dict[str, int]]:
        """
        Check if request is allowed under rate limit
        
        Args:
            key: Unique identifier for rate limit (e.g., IP, user_id)
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            use_redis: Whether to use Redis (for distributed) or local cache
            
        Returns:
            (is_allowed, {remaining: int, reset_time: int})
        """
        now = time.time()
        
        if use_redis:
            return await self._check_redis_limit(key, limit, window_seconds, now)
        else:
            return self._check_local_limit(key, limit, window_seconds, now)
    
    async def _check_redis_limit(self, key: str, limit: int, window_seconds: int, now: float) -> tuple[bool, Dict[str, int]]:
        """Redis-based sliding window rate limiter"""
        pipe = self.redis.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(f"rate_limit:{key}", 0, now - window_seconds)
        
        # Count current requests
        pipe.zcard(f"rate_limit:{key}")
        
        # Add current request
        pipe.zadd(f"rate_limit:{key}", {str(now): now})
        
        # Set expiry
        pipe.expire(f"rate_limit:{key}", window_seconds + 1)
        
        results = await pipe.execute()
        current_count = results[1]
        
        is_allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)
        reset_time = int(now + window_seconds)
        
        return is_allowed, {"remaining": remaining, "reset_time": reset_time}
    
    def _check_local_limit(self, key: str, limit: int, window_seconds: int, now: float) -> tuple[bool, Dict[str, int]]:
        """Local sliding window rate limiter"""
        window = self.local_cache[key]
        
        # Remove expired entries
        while window and window[0] <= now - window_seconds:
            window.popleft()
        
        is_allowed = len(window) < limit
        
        if is_allowed:
            window.append(now)
        
        remaining = max(0, limit - len(window))
        reset_time = int(now + window_seconds)
        
        return is_allowed, {"remaining": remaining, "reset_time": reset_time}