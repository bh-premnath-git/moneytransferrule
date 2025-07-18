import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open" # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5        # Number of failures to open circuit
    recovery_timeout: int = 60        # Seconds before attempting recovery
    success_threshold: int = 3        # Successes needed to close circuit
    timeout: float = 5.0              # Request timeout in seconds

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.logger = get_logger(f"circuit_breaker.{name}")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time < self.config.recovery_timeout:
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
            else:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.logger.info("circuit_breaker_half_open", name=self.name)
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs),
                timeout=self.config.timeout
            )
            
            # Handle success
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure(e)
            raise
    
    async def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info("circuit_breaker_closed", name=self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    async def _on_failure(self, exception: Exception):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.error(
                "circuit_breaker_opened", 
                name=self.name, 
                failure_count=self.failure_count,
                error=str(exception)
            )

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass