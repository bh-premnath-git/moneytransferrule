import logging
import time
from typing import List, Dict, Any, Optional, Union
from functools import lru_cache
from dataclasses import dataclass
from .eval_safe import safe_eval
from .models import RuleModel

# Performance and monitoring
logger = logging.getLogger(__name__)

@dataclass
class RuleExecutionMetrics:
    """Track rule execution performance and failures"""
    rule_id: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_execution_time: float = 0.0
    last_failure: Optional[str] = None

class RuleEngine:
    def __init__(self):
        self.rules: List[RuleModel] = []
        self.metrics: Dict[str, RuleExecutionMetrics] = {}
        self._expression_cache: Dict[str, bool] = {}
        self._cache_max_size = 1000
    
    def load(self, objs: List[RuleModel]) -> None:
        """Runtime hot-reload with validation"""
        valid_rules = []
        for rule in objs:
            if rule.enabled:
                # Pre-validate all expressions to catch errors early
                if self._validate_rule_expressions(rule):
                    valid_rules.append(rule)
                else:
                    logger.error(f"Rule {rule.id} has invalid expressions, skipping")
        
        self.rules = valid_rules
        logger.info(f"Loaded {len(self.rules)} valid rules")
    
    def _validate_rule_expressions(self, rule: RuleModel) -> bool:
        """Pre-validate all expressions in a rule"""
        try:
            test_ctx = {"amount": 100, "method": "CARD", "destination_country": "US"}
            
            if rule.routing:
                safe_eval(rule.routing.match, test_ctx)
            elif rule.fraud:
                safe_eval(rule.fraud.expression, test_ctx)
            elif rule.compliance:
                safe_eval(rule.compliance.expression, test_ctx)
            elif rule.business:
                safe_eval(rule.business.condition, test_ctx)
            
            return True
        except Exception as e:
            logger.error(f"Expression validation failed for rule {rule.id}: {e}")
            return False
    
    @lru_cache(maxsize=1000)
    def _cached_eval(self, expression: str, ctx_hash: str, ctx_dict: tuple) -> bool:
        """Cached expression evaluation for performance"""
        return safe_eval(expression, dict(ctx_dict))
    
    def _safe_eval_with_metrics(self, expression: str, ctx: dict, rule_id: str) -> bool:
        """Evaluate expression with error handling and metrics"""
        start_time = time.time()
        
        try:
            # Create hashable context for caching
            ctx_items = tuple(sorted(ctx.items()))
            ctx_hash = str(hash(ctx_items))
            
            result = self._cached_eval(expression, ctx_hash, ctx_items)
            
            # Update metrics
            self._update_metrics(rule_id, True, time.time() - start_time)
            return result
            
        except Exception as e:
            self._update_metrics(rule_id, False, time.time() - start_time, str(e))
            logger.warning(f"Expression evaluation failed for rule {rule_id}: {e}")
            return False
    
    def _update_metrics(self, rule_id: str, success: bool, execution_time: float, error: Optional[str] = None):
        """Update rule execution metrics"""
        if rule_id not in self.metrics:
            self.metrics[rule_id] = RuleExecutionMetrics(rule_id)
        
        metric = self.metrics[rule_id]
        metric.execution_count += 1
        
        if success:
            metric.success_count += 1
        else:
            metric.failure_count += 1
            metric.last_failure = error
        
        # Update rolling average execution time
        metric.avg_execution_time = (
            (metric.avg_execution_time * (metric.execution_count - 1) + execution_time) 
            / metric.execution_count
        )
    
    def route(self, ctx) -> Optional[List[str]]:
        """Routing with improved load balancing and error handling"""
        candidates = []
        
        for rule in self.rules:
            if not rule.routing:
                continue
                
            # Check if method is supported
            if hasattr(ctx, 'method') and ctx.method not in rule.routing.methods:
                continue
            
            # Evaluate routing condition
            if self._safe_eval_with_metrics(rule.routing.match, ctx.__dict__, rule.id):
                candidates.append(rule.routing)
        
        if not candidates:
            logger.info("No routing rules matched")
            return None
        
        # Sort by priority (lower number = higher priority)
        candidates.sort(key=lambda r: r.priority)
        
        # Use highest priority rule
        selected_rule = candidates[0]
        
        # Improved load balancing: higher weight = higher probability
        # But for simplicity, we'll use weight for ordering within same priority
        processors = list(selected_rule.processors)
        
        # Sort processors by weight (higher weight first)
        if selected_rule.weight > 0:
            # For weighted routing, we can implement more sophisticated logic
            # For now, we'll just return the processors in order
            return processors
        else:
            # Fallback to round-robin or random if no weight
            return processors
    
    def fraud(self, ctx) -> Dict[str, Any]:
        """Improved fraud detection with per-rule thresholds"""
        total_score = 0.0
        highest_action = "ALLOW"
        action_priority = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}
        
        matched_rules = []
        
        for rule in self.rules:
            if not rule.fraud:
                continue
            
            # Evaluate fraud condition
            if self._safe_eval_with_metrics(rule.fraud.expression, ctx.__dict__, rule.id):
                rule_score = rule.fraud.score_weight
                total_score += rule_score
                
                # Check individual rule threshold
                if rule_score >= rule.fraud.threshold:
                    if action_priority[rule.fraud.action] > action_priority[highest_action]:
                        highest_action = rule.fraud.action
                
                matched_rules.append({
                    "rule_id": rule.id,
                    "rule_name": rule.fraud.name,
                    "score": rule_score,
                    "threshold": rule.fraud.threshold,
                    "action": rule.fraud.action
                })
        
        return {
            "total_score": total_score,
            "action": highest_action,
            "matched_rules": matched_rules
        }
    
    def compliance(self, ctx) -> Dict[str, Any]:
        """Enhanced compliance checking with mandatory rule handling"""
        results = {}
        mandatory_failures = []
        
        for rule in self.rules:
            if not rule.compliance:
                continue
            
            # Evaluate compliance condition
            result = self._safe_eval_with_metrics(rule.compliance.expression, ctx.__dict__, rule.id)
            
            results[rule.compliance.name] = {
                "passed": result,
                "mandatory": rule.compliance.mandatory,
                "regulation": rule.compliance.regulation,
                "countries": rule.compliance.countries
            }
            
            if rule.compliance.mandatory and not result:
                mandatory_failures.append(rule.compliance.name)
        
        return {
            "results": results,
            "mandatory_failures": mandatory_failures,
            "overall_pass": len(mandatory_failures) == 0
        }
    
    def business(self, ctx) -> List[Dict[str, Any]]:
        """Enhanced business rule evaluation with action details"""
        actions = []
        
        for rule in self.rules:
            if not rule.business:
                continue
            
            # Evaluate business condition
            if self._safe_eval_with_metrics(rule.business.condition, ctx.__dict__, rule.id):
                actions.append({
                    "rule_id": rule.id,
                    "rule_name": rule.business.name,
                    "action": rule.business.action,
                    "discount": rule.business.discount,
                    "tags": rule.business.tags
                })
        
        return actions
    
    def get_metrics(self) -> Dict[str, RuleExecutionMetrics]:
        """Get rule execution metrics for monitoring"""
        return self.metrics.copy()
    
    def clear_cache(self) -> None:
        """Clear expression evaluation cache"""
        self._cached_eval.cache_clear()
        logger.info("Expression cache cleared")
    
    def health_check(self) -> Dict[str, Any]:
        """Engine health check for monitoring"""
        total_rules = len(self.rules)
        total_executions = sum(m.execution_count for m in self.metrics.values())
        total_failures = sum(m.failure_count for m in self.metrics.values())
        
        return {
            "status": "healthy",
            "total_rules": total_rules,
            "total_executions": total_executions,
            "total_failures": total_failures,
            "failure_rate": total_failures / max(total_executions, 1),
            "cache_info": self._cached_eval.cache_info()._asdict()
        }
