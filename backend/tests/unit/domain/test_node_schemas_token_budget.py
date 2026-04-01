from domain.value_objects.node_schemas import validate_node_config
from domain.value_objects.node_types import NodeType


def test_agent_node_accepts_token_budget():
    errors = validate_node_config(
        NodeType.AGENT.value,
        {
            "model": "gpt-4.1-mini",
            "tools": ["crm_lookup"],
            "token_budget": 1200,
        },
    )

    assert errors == []


def test_agent_node_rejects_non_positive_token_budget():
    errors = validate_node_config(
        NodeType.AGENT.value,
        {
            "model": "gpt-4.1-mini",
            "tools": ["crm_lookup"],
            "token_budget": 0,
        },
    )

    assert errors
    assert errors[0]["field"] == "token_budget"
