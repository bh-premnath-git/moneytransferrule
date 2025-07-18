import structlog
import logging.config
from typing import Any, Dict
import sys
import json

def configure_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """Configure structured logging with structlog"""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if environment == "production" 
            else structlog.dev.ConsoleRenderer(colors=True)
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'json': {
                'format': '%(message)s'
            },
            'console': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'json' if environment == "production" else 'console',
                'stream': sys.stdout
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'json',
                'filename': '/app/logs/rules-engine.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        },
        'loggers': {
            'app': {
                'handlers': ['console', 'file'],
                'level': log_level,
                'propagate': False
            },
            'uvicorn': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False
            },
            'confluent_kafka': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            }
        },
        'root': {
            'handlers': ['console'],
            'level': log_level
        }
    }
    
    logging.config.dictConfig(logging_config)

# Enhanced logging utilities
def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger"""
    return structlog.get_logger(name)

def log_rule_evaluation(logger: structlog.stdlib.BoundLogger, 
                       rule_id: str, 
                       rule_type: str, 
                       context: Dict[str, Any], 
                       result: Any, 
                       execution_time: float) -> None:
    """Log rule evaluation with structured data"""
    logger.info(
        "rule_evaluated",
        rule_id=rule_id,
        rule_type=rule_type,
        execution_time_ms=execution_time * 1000,
        context_summary={
            "amount": context.get("amount"),
            "method": context.get("method"),
            "country": context.get("destination_country")
        },
        result_summary=_summarize_result(result)
    )

def _summarize_result(result: Any) -> Dict[str, Any]:
    """Summarize rule evaluation result for logging"""
    if isinstance(result, dict):
        return {k: str(v)[:100] for k, v in result.items()}  # Truncate long values
    elif isinstance(result, list):
        return {"count": len(result), "items": [str(item)[:50] for item in result[:3]]}
    else:
        return {"value": str(result)[:100]}