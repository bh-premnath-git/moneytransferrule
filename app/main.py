from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import time
import asyncio
import logging
import os
from .engine import RuleEngine
from .redis_store import get_redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Money Transfer Rules Engine",
    description="A high-performance rules engine for money transfer processing",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = RuleEngine()
app.state.engine = engine


class Context(BaseModel):
    """Enhanced transaction context for rule evaluation"""

    txn_id: str
    destination_country: str
    source_country: str = "US"
    amount: float = Field(..., gt=0)
    method: str
    daily_txn_count: int = Field(..., ge=0)
    monthly_txn_count: int = Field(default=0, ge=0)
    customer_risk_score: Optional[float] = Field(default=None, ge=0, le=100)
    customer_tier: Optional[str] = "standard"
    currency: str = "USD"
    merchant_id: Optional[str] = None
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class EvaluationResponse(BaseModel):
    """Structured response for rule evaluation"""

    success: bool
    processors: List[str]
    fraud: Dict[str, Any]
    compliance: Dict[str, Any]
    business: List[Dict[str, Any]]
    execution_time_ms: float
    rules_evaluated: int


# Global tasks for graceful shutdown
background_tasks = []


async def load_sample_rules():
    """Load sample rules if enabled and none exist"""
    try:
        # Check if we should load sample rules
        load_samples = os.getenv("LOAD_SAMPLE_RULES", "false").lower() == "true"
        if not load_samples:
            logger.info("Sample rules loading disabled")
            return

        redis = await get_redis()

        # Check if rules already exist
        existing_rules = []
        async for key in redis.scan_iter(match="rule:*"):
            existing_rules.append(key)

        if existing_rules:
            logger.info(
                f"Found {len(existing_rules)} existing rules, skipping sample loading"
            )
            return

        # Import sample rules creation
        from .models import (
            RuleModel,
            RoutingRuleModel,
            FraudRuleModel,
            ComplianceRuleModel,
            BusinessRuleModel,
        )

        logger.info("Loading sample rules...")

        # Create sample rules
        rules = [
            RuleModel(
                id="route_card_us_ca",
                enabled=True,
                description="Route card transactions from US to CA",
                routing=RoutingRuleModel(
                    name="US to CA Card Route",
                    match="method == 'CARD' and source_country == 'US' and destination_country == 'CA'",
                    methods=["CARD"],
                    processors=["stripe", "adyen", "worldpay"],
                    priority=1,
                    weight=1.0,
                ),
            ),
            RuleModel(
                id="fraud_high_amount",
                enabled=True,
                description="High amount fraud detection",
                fraud=FraudRuleModel(
                    name="High Amount Check",
                    expression="amount > 5000",
                    score_weight=8.0,
                    threshold=20.0,
                    action="REVIEW",
                ),
            ),
            RuleModel(
                id="compliance_daily_limit",
                enabled=True,
                description="Daily transaction limit compliance",
                compliance=ComplianceRuleModel(
                    name="Daily Limit Check",
                    expression="daily_txn_count <= 10",
                    mandatory=True,
                    regulation="AML",
                    countries=["US", "CA"],
                ),
            ),
            RuleModel(
                id="business_vip_discount",
                enabled=True,
                description="VIP customer discount",
                business=BusinessRuleModel(
                    name="VIP Customer Discount",
                    condition="customer_tier == 'vip'",
                    action="apply_discount",
                    discount=5.0,
                    tags=["vip", "discount"],
                ),
            ),
        ]

        # Load rules into Redis using protobuf when available
        from .models import pydantic_to_proto_rule

        for rule in rules:
            rule_key = f"rule:{rule.id}"
            try:
                proto_rule = pydantic_to_proto_rule(rule)
                await redis.set(rule_key, proto_rule.SerializeToString())
            except Exception as e:
                logger.warning(f"Falling back to JSON for {rule.id}: {e}")
                if hasattr(rule, "model_dump_json"):
                    rule_data = rule.model_dump_json()
                else:
                    rule_data = rule.json()
                await redis.set(rule_key, rule_data)

        # Load rules into engine from Redis
        await load_rules_from_redis()

        logger.info(f"✅ Successfully loaded {len(rules)} sample rules")

    except Exception as e:
        logger.error(f"Failed to load sample rules: {e}")
        # Don't raise - sample rules are optional


async def load_rules_from_redis():
    """Load all rules from Redis into the engine"""
    try:
        import json
        from .models import RuleModel

        redis = await get_redis()

        rules = []
        async for key in redis.scan_iter(match="rule:*"):
            rule_data = await redis.get(key)
            if not rule_data:
                continue

            try:
                rule = None
                if isinstance(rule_data, bytes):
                    # Try protobuf first
                    try:
                        from .proto_gen import rules_pb2
                        from .models import proto_to_pydantic_rule

                        proto_rule = rules_pb2.Rule()
                        proto_rule.ParseFromString(rule_data)
                        rule = proto_to_pydantic_rule(proto_rule)
                    except Exception:
                        # Fallback to JSON
                        try:
                            rule_json = rule_data.decode("utf-8")
                            rule_dict = json.loads(rule_json)
                            if hasattr(RuleModel, "model_validate"):
                                rule = RuleModel.model_validate(rule_dict)
                            else:
                                rule = RuleModel.parse_obj(rule_dict)
                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            raise ValueError(f"Invalid rule data: {e}")
                else:
                    rule_dict = (
                        json.loads(rule_data)
                        if isinstance(rule_data, str)
                        else rule_data
                    )
                    if hasattr(RuleModel, "model_validate"):
                        rule = RuleModel.model_validate(rule_dict)
                    else:
                        rule = RuleModel.parse_obj(rule_dict)

                if rule:
                    rules.append(rule)
            except Exception as e:
                logger.warning(f"Failed to parse rule {key}: {e}")

        engine.load(rules)
        logger.info(f"Loaded {len(rules)} rules from Redis into engine")

    except Exception as e:
        logger.error(f"Failed to load rules from Redis: {e}")


@app.on_event("startup")
async def start_services():
    """Initialize all services on startup"""
    try:
        from . import kafka_consumer, grpc_server

        redis = await get_redis()

        # Test Redis connection
        await redis.ping()
        logger.info("Redis connection established")

        # Load sample rules if enabled
        await load_sample_rules()

        # Load existing rules from Redis
        await load_rules_from_redis()

        # Start background services
        kafka_task = asyncio.create_task(kafka_consumer.start(engine, redis))
        grpc_task = asyncio.create_task(grpc_server.serve(engine, redis))

        # Store tasks for graceful shutdown
        background_tasks.extend([kafka_task, grpc_task])

        logger.info("All services started successfully")
    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_services():
    """Gracefully shutdown background services"""
    logger.info("Shutting down services...")
    for task in background_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("All services shut down")


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(ctx: Context):
    """Evaluate all rules for a transaction context"""
    start_time = time.time()

    try:
        # Get routing decision
        route = engine.route(ctx)
        if not route:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No routing rule matched the transaction context",
            )

        # Get fraud assessment
        fraud_result = engine.fraud(ctx)

        # Get compliance check
        compliance_result = engine.compliance(ctx)

        # Get business rules
        business_result = engine.business(ctx)

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000

        return EvaluationResponse(
            success=True,
            processors=route,
            fraud=fraud_result,
            compliance=compliance_result,
            business=business_result,
            execution_time_ms=execution_time,
            rules_evaluated=len(engine.rules),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rule evaluation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rule evaluation failed: {str(e)}",
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        health_info = engine.health_check()
        return {"status": "healthy", "timestamp": time.time(), "engine": health_info}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )


@app.get("/metrics")
async def get_metrics():
    """Get detailed rule execution metrics"""
    try:
        metrics = engine.get_metrics()
        return {
            "timestamp": time.time(),
            "total_rules": len(engine.rules),
            "rule_metrics": {
                rule_id: {
                    "execution_count": metric.execution_count,
                    "success_count": metric.success_count,
                    "failure_count": metric.failure_count,
                    "avg_execution_time": metric.avg_execution_time,
                    "success_rate": metric.success_count
                    / max(metric.execution_count, 1),
                    "last_failure": metric.last_failure,
                }
                for rule_id, metric in metrics.items()
            },
        }
    except Exception as e:
        logger.error(f"Metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics retrieval failed: {str(e)}",
        )


@app.post("/cache/clear")
async def clear_cache():
    """Clear expression evaluation cache"""
    try:
        engine.clear_cache()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache clear failed: {str(e)}",
        )


@app.get("/rules/count")
async def get_rule_count():
    """Get current rule counts by type"""
    try:
        counts = {
            "total": len(engine.rules),
            "routing": sum(1 for r in engine.rules if r.routing),
            "fraud": sum(1 for r in engine.rules if r.fraud),
            "compliance": sum(1 for r in engine.rules if r.compliance),
            "business": sum(1 for r in engine.rules if r.business),
            "enabled": sum(1 for r in engine.rules if r.enabled),
        }
        return counts
    except Exception as e:
        logger.error(f"Rule count retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rule count retrieval failed: {str(e)}",
        )


# Add error handlers for better error responses
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
