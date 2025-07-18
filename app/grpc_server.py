import grpc
import asyncio
import json
import logging
from typing import Optional
from proto_gen import rules_pb2, rules_pb2_grpc
from models import RuleModel, proto_to_pydantic_rule, pydantic_to_proto_rule, create_proto_response
from engine import RuleEngine

logger = logging.getLogger(__name__)

class RuleService(rules_pb2_grpc.RuleServiceServicer):
    def __init__(self, engine: RuleEngine, redis):
        self.engine = engine
        self.redis = redis
        logger.info("RuleService initialized")

    async def CreateRule(self, request: rules_pb2.CreateRuleRequest, context) -> rules_pb2.RuleResponse:
        """Create a new rule"""
        try:
            # Convert proto to Pydantic model
            pydantic_rule = proto_to_pydantic_rule(request.rule)
            
            # Validate the rule
            if not pydantic_rule.id:
                return create_proto_response(
                    success=False,
                    message="Rule ID is required",
                    errors=[{"field": "id", "message": "Rule ID cannot be empty", "code": "REQUIRED_FIELD"}]
                )
            
            # Store in Redis
            rule_key = f"rule:{pydantic_rule.id}"
            await self.redis.set(rule_key, request.rule.SerializeToString())
            
            # Update engine with new rule
            updated_rules = [pydantic_rule] + [r for r in self.engine.rules if r.id != pydantic_rule.id]
            self.engine.load(updated_rules)
            
            logger.info(f"Created rule {pydantic_rule.id}")
            return create_proto_response(
                success=True,
                message=f"Rule {pydantic_rule.id} created successfully",
                rule=pydantic_rule
            )
            
        except Exception as e:
            logger.error(f"CreateRule failed: {e}")
            return create_proto_response(
                success=False,
                message=f"Failed to create rule: {str(e)}",
                errors=[{"field": "general", "message": str(e), "code": "INTERNAL_ERROR"}]
            )

    async def UpdateRule(self, request: rules_pb2.UpdateRuleRequest, context) -> rules_pb2.RuleResponse:
        """Update an existing rule"""
        try:
            # Convert proto to Pydantic model
            pydantic_rule = proto_to_pydantic_rule(request.rule)
            
            # Verify rule exists
            rule_key = f"rule:{request.rule_id}"
            existing_rule = await self.redis.get(rule_key)
            if not existing_rule:
                return create_proto_response(
                    success=False,
                    message=f"Rule {request.rule_id} not found",
                    errors=[{"field": "rule_id", "message": "Rule does not exist", "code": "NOT_FOUND"}]
                )
            
            # Update the rule ID to match the request
            pydantic_rule.id = request.rule_id
            
            # Store updated rule in Redis
            updated_proto = pydantic_to_proto_rule(pydantic_rule)
            await self.redis.set(rule_key, updated_proto.SerializeToString())
            
            # Update engine
            updated_rules = [pydantic_rule] + [r for r in self.engine.rules if r.id != request.rule_id]
            self.engine.load(updated_rules)
            
            logger.info(f"Updated rule {request.rule_id}")
            return create_proto_response(
                success=True,
                message=f"Rule {request.rule_id} updated successfully",
                rule=pydantic_rule
            )
            
        except Exception as e:
            logger.error(f"UpdateRule failed: {e}")
            return create_proto_response(
                success=False,
                message=f"Failed to update rule: {str(e)}",
                errors=[{"field": "general", "message": str(e), "code": "INTERNAL_ERROR"}]
            )

    async def GetRule(self, request: rules_pb2.GetRuleRequest, context) -> rules_pb2.RuleResponse:
        """Get a specific rule by ID"""
        try:
            rule_key = f"rule:{request.rule_id}"
            rule_data = await self.redis.get(rule_key)
            
            if not rule_data:
                return create_proto_response(
                    success=False,
                    message=f"Rule {request.rule_id} not found",
                    errors=[{"field": "rule_id", "message": "Rule does not exist", "code": "NOT_FOUND"}]
                )
            
            # Parse the proto rule
            proto_rule = rules_pb2.Rule()
            proto_rule.ParseFromString(rule_data)
            
            # Convert to Pydantic for response
            pydantic_rule = proto_to_pydantic_rule(proto_rule)
            
            logger.info(f"Retrieved rule {request.rule_id}")
            return create_proto_response(
                success=True,
                message=f"Rule {request.rule_id} retrieved successfully",
                rule=pydantic_rule
            )
            
        except Exception as e:
            logger.error(f"GetRule failed: {e}")
            return create_proto_response(
                success=False,
                message=f"Failed to get rule: {str(e)}",
                errors=[{"field": "general", "message": str(e), "code": "INTERNAL_ERROR"}]
            )

    async def ListRules(self, request: rules_pb2.ListRulesRequest, context) -> rules_pb2.RuleListResponse:
        """List rules with pagination"""
        try:
            # Get all rule keys from Redis
            rule_keys = []
            async for key in self.redis.scan_iter(match="rule:*"):
                rule_keys.append(key)
            
            # Apply filtering
            filtered_rules = []
            for key in rule_keys:
                rule_data = await self.redis.get(key)
                if rule_data:
                    proto_rule = rules_pb2.Rule()
                    proto_rule.ParseFromString(rule_data)
                    
                    # Apply enabled filter if requested
                    if request.enabled_only and not proto_rule.enabled:
                        continue
                    
                    # Add basic text filtering if filter is provided
                    if request.filter:
                        rule_text = f"{proto_rule.id} {proto_rule.description}".lower()
                        if request.filter.lower() not in rule_text:
                            continue
                    
                    filtered_rules.append(proto_rule)
            
            # Apply pagination
            page = max(1, request.page) if request.page else 1
            page_size = min(1000, max(1, request.page_size)) if request.page_size else 50
            
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_rules = filtered_rules[start_idx:end_idx]
            
            # Create response
            response = rules_pb2.RuleListResponse()
            response.success = True
            response.message = f"Retrieved {len(paginated_rules)} rules"
            response.rules.extend(paginated_rules)
            response.total_count = len(filtered_rules)
            response.page = page
            response.page_size = page_size
            
            logger.info(f"Listed {len(paginated_rules)} rules (page {page})")
            return response
            
        except Exception as e:
            logger.error(f"ListRules failed: {e}")
            response = rules_pb2.RuleListResponse()
            response.success = False
            response.message = f"Failed to list rules: {str(e)}"
            return response

    async def DeleteRule(self, request: rules_pb2.DeleteRuleRequest, context) -> rules_pb2.RuleResponse:
        """Delete a rule by ID"""
        try:
            rule_key = f"rule:{request.rule_id}"
            
            # Check if rule exists
            existing_rule = await self.redis.get(rule_key)
            if not existing_rule:
                return create_proto_response(
                    success=False,
                    message=f"Rule {request.rule_id} not found",
                    errors=[{"field": "rule_id", "message": "Rule does not exist", "code": "NOT_FOUND"}]
                )
            
            # Delete from Redis
            await self.redis.delete(rule_key)
            
            # Update engine (remove the rule)
            updated_rules = [r for r in self.engine.rules if r.id != request.rule_id]
            self.engine.load(updated_rules)
            
            logger.info(f"Deleted rule {request.rule_id}")
            return create_proto_response(
                success=True,
                message=f"Rule {request.rule_id} deleted successfully"
            )
            
        except Exception as e:
            logger.error(f"DeleteRule failed: {e}")
            return create_proto_response(
                success=False,
                message=f"Failed to delete rule: {str(e)}",
                errors=[{"field": "general", "message": str(e), "code": "INTERNAL_ERROR"}]
            )

    async def EvaluateRules(self, request: rules_pb2.EvaluateRulesRequest, context) -> rules_pb2.EvaluateRulesResponse:
        """Evaluate rules against a transaction context"""
        try:
            # Convert context map to dict
            ctx_dict = dict(request.context)
            
            # Create a simple context object
            class SimpleContext:
                def __init__(self, data):
                    self.__dict__.update(data)
            
            ctx = SimpleContext(ctx_dict)
            
            # Evaluate rules based on requested types
            results = []
            requested_types = set(request.rule_types) if request.rule_types else {"routing", "fraud", "compliance", "business"}
            
            if "routing" in requested_types:
                routing_result = self.engine.route(ctx)
                if routing_result:
                    for processor in routing_result:
                        result = rules_pb2.RuleEvaluationResult()
                        result.rule_id = "routing"
                        result.rule_name = "Routing Decision"
                        result.matched = True
                        result.action = processor
                        result.metadata["processor"] = processor
                        results.append(result)
            
            if "fraud" in requested_types:
                fraud_result = self.engine.fraud(ctx)
                result = rules_pb2.RuleEvaluationResult()
                result.rule_id = "fraud"
                result.rule_name = "Fraud Assessment"
                result.matched = fraud_result.get("total_score", 0) > 0
                result.score = fraud_result.get("total_score", 0)
                result.action = fraud_result.get("action", "ALLOW")
                result.metadata["total_score"] = str(fraud_result.get("total_score", 0))
                results.append(result)
            
            if "compliance" in requested_types:
                compliance_result = self.engine.compliance(ctx)
                result = rules_pb2.RuleEvaluationResult()
                result.rule_id = "compliance"
                result.rule_name = "Compliance Check"
                result.matched = compliance_result.get("overall_pass", False)
                result.action = "PASS" if compliance_result.get("overall_pass", False) else "FAIL"
                result.metadata["mandatory_failures"] = str(len(compliance_result.get("mandatory_failures", [])))
                results.append(result)
            
            if "business" in requested_types:
                business_result = self.engine.business(ctx)
                for business_action in business_result:
                    result = rules_pb2.RuleEvaluationResult()
                    result.rule_id = business_action.get("rule_id", "business")
                    result.rule_name = business_action.get("rule_name", "Business Rule")
                    result.matched = True
                    result.action = business_action.get("action", "")
                    result.metadata["discount"] = str(business_action.get("discount", 0))
                    results.append(result)
            
            # Create response
            response = rules_pb2.EvaluateRulesResponse()
            response.success = True
            response.message = f"Evaluated {len(results)} rule results"
            response.results.extend(results)
            
            logger.info(f"Evaluated rules for context with {len(results)} results")
            return response
            
        except Exception as e:
            logger.error(f"EvaluateRules failed: {e}")
            response = rules_pb2.EvaluateRulesResponse()
            response.success = False
            response.message = f"Failed to evaluate rules: {str(e)}"
            return response

async def serve(engine: RuleEngine, redis, port: int = 50051):
    """Start the gRPC server"""
    try:
        server = grpc.aio.server()
        rules_pb2_grpc.add_RuleServiceServicer_to_server(RuleService(engine, redis), server)
        
        listen_addr = f"[::]:{port}"
        server.add_insecure_port(listen_addr)
        
        logger.info(f"Starting gRPC server on {listen_addr}")
        await server.start()
        
        try:
            await server.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Shutting down gRPC server...")
            await server.stop(5)
            
    except Exception as e:
        logger.error(f"gRPC server failed: {e}")
        raise
