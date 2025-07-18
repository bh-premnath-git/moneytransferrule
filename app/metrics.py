rom prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
from typing import Dict, Any
import time
import functools
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Prometheus metrics
RULE_EVALUATIONS = Counter(
    'rule_evaluations_total',
    'Total number of rule evaluations',
    ['rule_type', 'rule_id', 'status']
)

RULE_EXECUTION_TIME = Histogram(
    'rule_execution_duration_seconds',
    'Time spent executing rules',
    ['rule_type', 'rule_id'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

ACTIVE_RULES = Gauge(
    'rules_loaded_total',
    'Number of active rules by type',
    ['rule_type']
)

CACHE_OPERATIONS = Counter(
    'expression_cache_operations_total',
    'Expression cache operations',
    ['operation']  # hit, miss, clear
)

HTTP_REQUESTS = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

REDIS_OPERATIONS = Counter(
    'redis_operations_total',
    'Redis operations',
    ['operation', 'status']
)

KAFKA_MESSAGES = Counter(
    'kafka_messages_total',
    'Kafka messages processed',
    ['topic', 'status']
)

SERVICE_INFO = Info(
    'service_info',
    'Service information'
)

class MetricsCollector:
    """Centralized metrics collection"""
    
    def __init__(self):
        self.start_time = time.time()
        
        # Set service info
        SERVICE_INFO.info({
            'version': '1.0.0',
            'python_version': '3.11',
            'environment': 'development'  # Should come from config
        })
    
    @contextmanager
    def time_rule_execution(self, rule_type: str, rule_id: str):
        """Context manager for timing rule execution"""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            RULE_EXECUTION_TIME.labels(rule_type=rule_type, rule_id=rule_id).observe(duration)
            RULE_EVALUATIONS.labels(rule_type=rule_type, rule_id=rule_id, status='success').inc()
        except Exception:
            duration = time.time() - start_time
            RULE_EXECUTION_TIME.labels(rule_type=rule_type, rule_id=rule_id).observe(duration)
            RULE_EVALUATIONS.labels(rule_type=rule_type, rule_id=rule_id, status='error').inc()
            raise
    
    @contextmanager
    def time_http_request(self, method: str, endpoint: str):
        """Context manager for timing HTTP requests"""
        start_time = time.time()
        status_code = 'unknown'
        try:
            yield
            status_code = '200'  # Default success
        except Exception as e:
            if hasattr(e, 'status_code'):
                status_code = str(e.status_code)
            else:
                status_code = '500'
            raise
        finally:
            duration = time.time() - start_time
            HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
            HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
    
    def update_active_rules(self, rules_by_type: Dict[str, int]):
        """Update active rules gauge"""
        for rule_type, count in rules_by_type.items():
            ACTIVE_RULES.labels(rule_type=rule_type).set(count)
    
    def record_cache_operation(self, operation: str):
        """Record cache operation (hit/miss/clear)"""
        CACHE_OPERATIONS.labels(operation=operation).inc()
    
    def record_redis_operation(self, operation: str, status: str):
        """Record Redis operation"""
        REDIS_OPERATIONS.labels(operation=operation, status=status).inc()
    
    def record_kafka_message(self, topic: str, status: str):
        """Record Kafka message processing"""
        KAFKA_MESSAGES.labels(topic=topic, status=status).inc()

# Global metrics collector
metrics = MetricsCollector()

def instrument_rule_execution(rule_type: str):
    """Decorator for instrumenting rule execution"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract rule_id from first argument if it's a rule object
            rule_id = 'unknown'
            if args and hasattr(args[0], 'id'):
                rule_id = args[0].id
            
            with metrics.time_rule_execution(rule_type, rule_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator

def instrument_http_endpoint(endpoint: str):
    """Decorator for instrumenting HTTP endpoints"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with metrics.time_http_request('POST', endpoint):  # Assume POST for now
                return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with metrics.time_http_request('POST', endpoint):
                return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator