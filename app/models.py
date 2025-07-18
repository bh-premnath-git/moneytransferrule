try:
    from pydantic.v1 import BaseModel, Field, conlist, confloat, validator, root_validator
except ImportError:  # Pydantic <2
    from pydantic import BaseModel, Field, conlist, confloat, validator, root_validator

from typing import List, Optional
from enum import Enum

from datetime import datetime
import uuid

class PaymentMethod(str, Enum):
    CARD = "CARD"
    CASH = "CASH"
    WALLET = "WALLET"
    BANK_TRANSFER = "BANK_TRANSFER"

class FraudAction(str, Enum):
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    ALLOW = "ALLOW"

class RoutingRuleModel(BaseModel):
    name: str
    match: str
    methods: conlist(PaymentMethod, min_items=1)
    processors: conlist(str, min_items=1)
    priority: int = Field(..., ge=1, le=1000)
    weight: confloat(ge=0.0, le=1.0) = 1.0
    


class FraudRuleModel(BaseModel):
    name: str
    expression: str
    score_weight: confloat(ge=0, le=10)
    threshold: confloat(ge=0, le=100)
    action: FraudAction

class ComplianceRuleModel(BaseModel):
    name: str
    expression: str
    mandatory: bool
    regulation: str
    countries: List[str] = []

class BusinessRuleModel(BaseModel):
    name: str
    condition: str
    action: str
    discount: confloat(ge=0, le=100) = 0
    tags: List[str] = []

class RuleModel(BaseModel):
    # Core fields matching proto
    id: str
    ts: datetime = Field(default_factory=datetime.now)
    enabled: bool = True
    description: str = ""
    version: str = "1.0.0"
    created_by: str = "system"
    last_modified: datetime = Field(default_factory=datetime.now)
    
    # Rule type definitions (exactly one should be set)
    routing: Optional[RoutingRuleModel] = None
    fraud: Optional[FraudRuleModel] = None
    compliance: Optional[ComplianceRuleModel] = None
    business: Optional[BusinessRuleModel] = None
    
    @root_validator(skip_on_failure=True)
    def exactly_one_rule_type(cls, values):
        """Ensure exactly one rule type is defined"""
        rule_types = ["routing", "fraud", "compliance", "business"]
        defined_rules = [r for r in rule_types if values.get(r) is not None]

        if len(defined_rules) == 0:
            raise ValueError("At least one rule type must be defined")
        elif len(defined_rules) > 1:
            raise ValueError(f"Only one rule type allowed, but found: {defined_rules}")

        return values
    
    @validator("id", pre=True, always=True)
    def generate_id_if_missing(cls, v):
        """Generate UUID if id is not provided"""
        return v or str(uuid.uuid4())
    
    @validator("last_modified", pre=True, always=True)
    def update_last_modified(cls, v):
        """Always update last_modified to current time"""
        return datetime.now()


# Proto-to-Pydantic conversion functions
def proto_to_pydantic_routing(proto_rule) -> RoutingRuleModel:
    """Convert proto RoutingRule to Pydantic RoutingRuleModel"""
    try:
        from .proto_gen import rules_pb2
    except ImportError:
        raise ImportError("Proto classes not generated. Run: ./scripts/gen_protos.sh")

    methods = [PaymentMethod[rules_pb2.PaymentMethod.Name(m)] for m in proto_rule.methods]
    return RoutingRuleModel(
        name=proto_rule.name,
        match=proto_rule.match,
        methods=methods,
        processors=list(proto_rule.processors),
        priority=proto_rule.priority,
        weight=proto_rule.weight
    )

def proto_to_pydantic_fraud(proto_rule) -> FraudRuleModel:
    """Convert proto FraudRule to Pydantic FraudRuleModel"""
    try:
        from .proto_gen import rules_pb2
    except ImportError:
        raise ImportError("Proto classes not generated. Run: ./scripts/gen_protos.sh")

    action = FraudAction[rules_pb2.FraudAction.Name(proto_rule.action)]
    return FraudRuleModel(
        name=proto_rule.name,
        expression=proto_rule.expression,
        score_weight=proto_rule.score_weight,
        threshold=proto_rule.threshold,
        action=action
    )

def proto_to_pydantic_compliance(proto_rule) -> ComplianceRuleModel:
    """Convert proto ComplianceRule to Pydantic ComplianceRuleModel"""
    return ComplianceRuleModel(
        name=proto_rule.name,
        expression=proto_rule.expression,
        mandatory=proto_rule.mandatory,
        regulation=proto_rule.regulation,
        countries=list(proto_rule.countries)
    )

def proto_to_pydantic_business(proto_rule) -> BusinessRuleModel:
    """Convert proto BusinessRule to Pydantic BusinessRuleModel"""
    return BusinessRuleModel(
        name=proto_rule.name,
        condition=proto_rule.condition,
        action=proto_rule.action,
        discount=proto_rule.discount,
        tags=list(proto_rule.tags)
    )

def proto_to_pydantic_rule(proto_rule) -> RuleModel:
    """Convert proto Rule to Pydantic RuleModel"""
    # Convert timestamps from proto to datetime
    ts = datetime.fromtimestamp(proto_rule.ts.seconds + proto_rule.ts.nanos / 1e9)
    last_modified = datetime.fromtimestamp(
        proto_rule.last_modified.seconds + proto_rule.last_modified.nanos / 1e9
    )
    
    # Base rule data
    rule_data = {
        "id": proto_rule.id,
        "ts": ts,
        "enabled": proto_rule.enabled,
        "description": proto_rule.description,
        "version": proto_rule.version,
        "created_by": proto_rule.created_by,
        "last_modified": last_modified,
    }
    
    # Add the specific rule type
    if proto_rule.HasField("routing"):
        rule_data["routing"] = proto_to_pydantic_routing(proto_rule.routing)
    elif proto_rule.HasField("fraud"):
        rule_data["fraud"] = proto_to_pydantic_fraud(proto_rule.fraud)
    elif proto_rule.HasField("compliance"):
        rule_data["compliance"] = proto_to_pydantic_compliance(proto_rule.compliance)
    elif proto_rule.HasField("business"):
        rule_data["business"] = proto_to_pydantic_business(proto_rule.business)
    
    return RuleModel(**rule_data)

def pydantic_to_proto_rule(pydantic_rule: RuleModel):
    """Convert Pydantic RuleModel to proto Rule"""
    try:
        from .proto_gen import rules_pb2
        from google.protobuf.timestamp_pb2 import Timestamp
    except ImportError:
        raise ImportError("Proto classes not generated. Run: ./scripts/gen_protos.ps1 or ./scripts/gen_protos.sh")
    
    # Create new proto rule
    proto_rule = rules_pb2.Rule()
    
    # Set basic fields
    proto_rule.id = pydantic_rule.id
    proto_rule.enabled = pydantic_rule.enabled
    proto_rule.description = pydantic_rule.description
    proto_rule.version = pydantic_rule.version
    proto_rule.created_by = pydantic_rule.created_by
    
    # Convert datetime to proto timestamp
    def datetime_to_timestamp(dt: datetime) -> Timestamp:
        timestamp = Timestamp()
        timestamp.FromDatetime(dt)
        return timestamp
    
    proto_rule.ts.CopyFrom(datetime_to_timestamp(pydantic_rule.ts))
    proto_rule.last_modified.CopyFrom(datetime_to_timestamp(pydantic_rule.last_modified))
    
    # Convert specific rule type
    if pydantic_rule.routing:
        routing_rule = rules_pb2.RoutingRule()
        routing_rule.name = pydantic_rule.routing.name
        routing_rule.match = pydantic_rule.routing.match
        routing_rule.methods[:] = [
            rules_pb2.PaymentMethod.Value(m.name) for m in pydantic_rule.routing.methods
        ]
        routing_rule.processors[:] = pydantic_rule.routing.processors
        routing_rule.priority = pydantic_rule.routing.priority
        routing_rule.weight = pydantic_rule.routing.weight
        proto_rule.routing.CopyFrom(routing_rule)
    
    elif pydantic_rule.fraud:
        fraud_rule = rules_pb2.FraudRule()
        fraud_rule.name = pydantic_rule.fraud.name
        fraud_rule.expression = pydantic_rule.fraud.expression
        fraud_rule.score_weight = pydantic_rule.fraud.score_weight
        fraud_rule.threshold = pydantic_rule.fraud.threshold
        fraud_rule.action = rules_pb2.FraudAction.Value(pydantic_rule.fraud.action.name)
        proto_rule.fraud.CopyFrom(fraud_rule)
    
    elif pydantic_rule.compliance:
        compliance_rule = rules_pb2.ComplianceRule()
        compliance_rule.name = pydantic_rule.compliance.name
        compliance_rule.expression = pydantic_rule.compliance.expression
        compliance_rule.mandatory = pydantic_rule.compliance.mandatory
        compliance_rule.regulation = pydantic_rule.compliance.regulation
        compliance_rule.countries[:] = pydantic_rule.compliance.countries
        proto_rule.compliance.CopyFrom(compliance_rule)
    
    elif pydantic_rule.business:
        business_rule = rules_pb2.BusinessRule()
        business_rule.name = pydantic_rule.business.name
        business_rule.condition = pydantic_rule.business.condition
        business_rule.action = pydantic_rule.business.action
        business_rule.discount = pydantic_rule.business.discount
        business_rule.tags[:] = pydantic_rule.business.tags
        proto_rule.business.CopyFrom(business_rule)
    
    else:
        raise ValueError("No rule type defined in Pydantic model")
    
    return proto_rule


def create_proto_response(success: bool, message: str, rule=None, errors=None):
    """Helper function to create proto RuleResponse"""
    try:
        from .proto_gen import rules_pb2
    except ImportError:
        raise ImportError("Proto classes not generated. Run: ./scripts/gen_protos.ps1 or ./scripts/gen_protos.sh")
    
    response = rules_pb2.RuleResponse()
    response.success = success
    response.message = message
    
    if rule:
        if isinstance(rule, RuleModel):
            response.rule.CopyFrom(pydantic_to_proto_rule(rule))
        else:
            response.rule.CopyFrom(rule)
    
    if errors:
        for error in errors:
            proto_error = rules_pb2.ValidationError()
            proto_error.field = error.get("field", "")
            proto_error.message = error.get("message", "")
            proto_error.code = error.get("code", "")
            response.errors.append(proto_error)
    
    return response
