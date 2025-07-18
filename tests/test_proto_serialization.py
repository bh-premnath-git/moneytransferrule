import pytest
from app.models import RuleModel, RoutingRuleModel, pydantic_to_proto_rule, proto_to_pydantic_rule


def test_proto_round_trip():
    pytest.importorskip("app.proto_gen.rules_pb2")

    rule = RuleModel(
        id="rt",
        routing=RoutingRuleModel(
            name="basic",
            match="amount > 0",
            methods=["CARD"],
            processors=["P1"],
            priority=1,
            weight=1.0,
        ),
    )

    proto = pydantic_to_proto_rule(rule)
    restored = proto_to_pydantic_rule(proto)

    assert restored.id == rule.id
    assert restored.routing.name == rule.routing.name
