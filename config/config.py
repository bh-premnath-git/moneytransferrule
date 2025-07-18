# app/config.py
from pydantic import BaseSettings, Field
from typing import Optional, List
import os

class RedisSettings(BaseSettings):
    """Redis configuration"""
    url: str = Field(default="redis://redis:6379", env="REDIS_URL")
    max_connections: int = Field(default=10, env="REDIS_MAX_CONNECTIONS")
    retry_on_timeout: bool = Field(default=True, env="REDIS_RETRY_ON_TIMEOUT")
    health_check_interval: int = Field(default=30, env="REDIS_HEALTH_CHECK_INTERVAL")

class KafkaSettings(BaseSettings):
    """Kafka configuration"""
    bootstrap_servers: str = Field(default="kafka:29092", env="KAFKA_BOOTSTRAP_SERVERS")
    topic: str = Field(default="rules", env="KAFKA_TOPIC")
    group_id: str = Field(default="rule_engine", env="KAFKA_GROUP_ID")
    auto_offset_reset: str = Field(default="earliest", env="KAFKA_AUTO_OFFSET_RESET")

class ServiceSettings(BaseSettings):
    """Service configuration"""
    rest_port: int = Field(default=8000, env="REST_PORT")
    grpc_port: int = Field(default=50051, env="GRPC_PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    load_sample_rules: bool = Field(default=False, env="LOAD_SAMPLE_RULES")
    
class SecuritySettings(BaseSettings):
    """Security configuration"""
    max_expression_length: int = Field(default=1000, env="MAX_EXPRESSION_LENGTH")
    expression_cache_size: int = Field(default=1000, env="EXPRESSION_CACHE_SIZE")
    rate_limit_requests: int = Field(default=1000, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=3600, env="RATE_LIMIT_WINDOW")

class MetricsSettings(BaseSettings):
    """Metrics and monitoring configuration"""
    enable_prometheus: bool = Field(default=True, env="ENABLE_PROMETHEUS")
    metrics_port: int = Field(default=9090, env="METRICS_PORT")
    health_check_timeout: float = Field(default=5.0, env="HEALTH_CHECK_TIMEOUT")

class Settings(BaseSettings):
    """Main application settings"""
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Sub-configurations
    redis: RedisSettings = RedisSettings()
    kafka: KafkaSettings = KafkaSettings()
    service: ServiceSettings = ServiceSettings()
    security: SecuritySettings = SecuritySettings()
    metrics: MetricsSettings = MetricsSettings()
    
    # CORS settings
    allowed_origins: List[str] = Field(
        default=["*"], 
        env="ALLOWED_ORIGINS",
        description="Comma-separated list of allowed origins"
    )
    
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Global settings instance
settings = Settings()