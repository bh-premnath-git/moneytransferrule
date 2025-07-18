from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import time
import asyncio
import logging
from .engine import RuleEngine
from .redis_store import get_redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Money Transfer Rules Engine",
    description="A high-performance rules engine for money transfer processing",
    version="1.0.0"
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

@app.on_event("startup")
async def start_services():
    """Initialize all services on startup"""
    try:
        from . import kafka_consumer, grpc_server
        redis = await get_redis()
        
        # Test Redis connection
        await redis.ping()
        logger.info("Redis connection established")
        
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
                detail="No routing rule matched the transaction context"
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
            rules_evaluated=len(engine.rules)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rule evaluation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rule evaluation failed: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        health_info = engine.health_check()
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "engine": health_info
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
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
                    "success_rate": metric.success_count / max(metric.execution_count, 1),
                    "last_failure": metric.last_failure
                }
                for rule_id, metric in metrics.items()
            }
        }
    except Exception as e:
        logger.error(f"Metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics retrieval failed: {str(e)}"
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
            detail=f"Cache clear failed: {str(e)}"
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
            "enabled": sum(1 for r in engine.rules if r.enabled)
        }
        return counts
    except Exception as e:
        logger.error(f"Rule count retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rule count retrieval failed: {str(e)}"
        )

# Add error handlers for better error responses
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=4)
