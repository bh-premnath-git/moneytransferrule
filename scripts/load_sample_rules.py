#!/usr/bin/env python3
"""
Load sample rules into the Money Transfer Rules Engine
"""

import asyncio
import json
from typing import List
import sys
import os

# Add the app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models import RuleModel, RoutingRuleModel, FraudRuleModel, ComplianceRuleModel, BusinessRuleModel
from app.redis_store import get_redis
from app.engine import RuleEngine

async def create_sample_rules() -> List[RuleModel]:
    """Create sample rules for testing"""
    rules = []
    
    # 1. Routing Rules
    routing_rule = RuleModel(
        id="route_card_us_ca",
        enabled=True,
        description="Route card transactions from US to CA",
        routing=RoutingRuleModel(
            name="US to CA Card Route",
            match="method == 'CARD' and source_country == 'US' and destination_country == 'CA'",
            methods=["CARD"],
            processors=["stripe", "adyen", "worldpay"],
            priority=1,
            weight=1.0
        )
    )
    rules.append(routing_rule)
    
    # 2. Fraud Rules
    fraud_rule = RuleModel(
        id="fraud_high_amount",
        enabled=True,
        description="High amount fraud detection",
        fraud=FraudRuleModel(
            name="High Amount Check",
            expression="amount > 5000",
            score_weight=8.0,
            threshold=20.0,
            action="REVIEW"
        )
    )
    rules.append(fraud_rule)
    
    # 3. Compliance Rules
    compliance_rule = RuleModel(
        id="compliance_daily_limit",
        enabled=True,
        description="Daily transaction limit compliance",
        compliance=ComplianceRuleModel(
            name="Daily Limit Check",
            expression="daily_txn_count <= 10",
            mandatory=True,
            regulation="AML",
            countries=["US", "CA"]
        )
    )
    rules.append(compliance_rule)
    
    # 4. Business Rules
    business_rule = RuleModel(
        id="business_vip_discount",
        enabled=True,
        description="VIP customer discount",
        business=BusinessRuleModel(
            name="VIP Customer Discount",
            condition="customer_tier == 'vip'",
            action="apply_discount",
            discount=5.0,
            tags=["vip", "discount"]
        )
    )
    rules.append(business_rule)
    
    return rules

async def load_rules_to_redis(rules: List[RuleModel]):
    """Load rules into Redis"""
    redis = await get_redis()
    
    for rule in rules:
        rule_key = f"rule:{rule.id}"
        rule_data = rule.model_dump_json()
        await redis.set(rule_key, rule_data)
        print(f"✅ Loaded rule: {rule.id}")
    
    print(f"\n🎉 Successfully loaded {len(rules)} rules to Redis!")

async def test_engine_with_rules():
    """Test the engine with loaded rules"""
    from app.main import Context
    
    # Create sample rules
    rules = await create_sample_rules()
    
    # Load into engine
    engine = RuleEngine()
    engine.load(rules)
    
    # Test context
    ctx = Context(
        txn_id="test-123",
        amount=1000,
        currency="USD",
        source_country="US",
        destination_country="CA",
        method="CARD",
        daily_txn_count=1,
        customer_tier="standard"
    )
    
    print("\n🧪 Testing Rules Engine:")
    print(f"📊 Loaded {len(engine.rules)} rules")
    
    # Test routing
    route = engine.route(ctx)
    print(f"🔀 Routing: {route}")
    
    # Test fraud
    fraud = engine.fraud(ctx)
    print(f"🚨 Fraud: {fraud}")
    
    # Test compliance
    compliance = engine.compliance(ctx)
    print(f"📋 Compliance: {compliance}")
    
    # Test business
    business = engine.business(ctx)
    print(f"💼 Business: {business}")

async def main():
    """Main function"""
    print("🚀 Loading Sample Rules for Money Transfer Engine\n")
    
    try:
        # Create sample rules
        rules = await create_sample_rules()
        
        # Load to Redis
        await load_rules_to_redis(rules)
        
        # Test engine
        await test_engine_with_rules()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
