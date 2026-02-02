"""
Unit tests for node configuration schemas.

Tests the JSON Schema-like validation rules for each node type.
"""

from domain.value_objects.node_schemas import (
    NODE_SCHEMAS,
    get_schema_for_type,
    validate_node_config,
)
from domain.value_objects.node_types import NodeType


class TestNodeSchemaRegistry:
    """Tests for schema registry completeness."""

    def test_all_node_types_have_schemas(self):
        """Every valid node type should have a schema."""
        for node_type in NodeType:
            schema = get_schema_for_type(node_type.value)
            assert schema is not None, f"Missing schema for {node_type.value}"

    def test_schema_count_matches_node_types(self):
        """Schema count should match node type count."""
        assert len(NODE_SCHEMAS) == len(NodeType)

    def test_get_schema_for_unknown_type_returns_none(self):
        """Unknown node type should return None."""
        assert get_schema_for_type("unknown_type") is None


class TestPromptNodeSchema:
    """Tests for prompt node config validation."""

    def test_empty_config_valid(self):
        """Prompt node has no required fields."""
        errors = validate_node_config("prompt", {})
        assert len(errors) == 0

    def test_valid_full_config(self):
        """Valid complete prompt config."""
        config = {
            "prompt_template": "Hello {{name}}",
            "system_prompt": "You are helpful.",
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000,
            "role": "assistant",
            "job_description": "Help users",
        }
        errors = validate_node_config("prompt", config)
        assert len(errors) == 0

    def test_temperature_below_min(self):
        """Temperature below 0 should fail."""
        config = {"temperature": -0.5}
        errors = validate_node_config("prompt", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "temperature"

    def test_temperature_above_max(self):
        """Temperature above 2 should fail."""
        config = {"temperature": 2.5}
        errors = validate_node_config("prompt", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "temperature"

    def test_temperature_at_boundaries(self):
        """Temperature at 0 and 2 should be valid."""
        assert len(validate_node_config("prompt", {"temperature": 0})) == 0
        assert len(validate_node_config("prompt", {"temperature": 2})) == 0

    def test_invalid_type_for_temperature(self):
        """Non-number temperature should fail."""
        config = {"temperature": "warm"}
        errors = validate_node_config("prompt", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "temperature"


class TestHttpNodeSchema:
    """Tests for HTTP node config validation."""

    def test_url_required(self):
        """URL is required for HTTP nodes."""
        errors = validate_node_config("http", {})
        assert len(errors) == 1
        assert errors[0]["field"] == "url"
        assert "Required" in errors[0]["message"]

    def test_url_empty_string_fails(self):
        """Empty URL string should fail."""
        errors = validate_node_config("http", {"url": ""})
        assert len(errors) == 1
        assert errors[0]["field"] == "url"

    def test_valid_url(self):
        """Valid URL should pass."""
        config = {"url": "https://api.example.com/endpoint"}
        errors = validate_node_config("http", config)
        assert len(errors) == 0

    def test_valid_method_values(self):
        """Valid HTTP methods should pass."""
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            config = {"url": "https://example.com", "method": method}
            errors = validate_node_config("http", config)
            assert len(errors) == 0, f"Method {method} should be valid"

    def test_invalid_method(self):
        """Invalid HTTP method should fail."""
        config = {"url": "https://example.com", "method": "INVALID"}
        errors = validate_node_config("http", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "method"


class TestTransformNodeSchema:
    """Tests for transform node config validation."""

    def test_expression_required(self):
        """Expression is required for transform nodes."""
        errors = validate_node_config("transform", {})
        assert len(errors) == 1
        assert errors[0]["field"] == "expression"

    def test_expression_empty_fails(self):
        """Empty expression should fail."""
        errors = validate_node_config("transform", {"expression": ""})
        assert len(errors) == 1
        assert errors[0]["field"] == "expression"

    def test_valid_expression(self):
        """Valid expression should pass."""
        config = {"expression": "data.name.toUpperCase()"}
        errors = validate_node_config("transform", config)
        assert len(errors) == 0


class TestMemoryNodeSchema:
    """Tests for memory node config validation."""

    def test_action_required(self):
        """Action is required for memory nodes."""
        errors = validate_node_config("memory", {})
        assert len(errors) == 1
        assert errors[0]["field"] == "action"

    def test_valid_action_values(self):
        """Valid action values should pass."""
        for action in ["get", "set", "delete"]:
            config = {"action": action}
            errors = validate_node_config("memory", config)
            assert len(errors) == 0, f"Action {action} should be valid"

    def test_invalid_action(self):
        """Invalid action should fail."""
        config = {"action": "update"}
        errors = validate_node_config("memory", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "action"

    def test_ttl_seconds_min(self):
        """TTL must be at least 0."""
        config = {"action": "set", "ttl_seconds": -1}
        errors = validate_node_config("memory", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "ttl_seconds"


class TestToolNodeSchema:
    """Tests for tool node config validation."""

    def test_tool_required(self):
        """Tool is required for tool nodes."""
        errors = validate_node_config("tool", {})
        assert len(errors) == 1
        assert errors[0]["field"] == "tool"

    def test_tool_empty_fails(self):
        """Empty tool name should fail."""
        errors = validate_node_config("tool", {"tool": ""})
        assert len(errors) == 1
        assert errors[0]["field"] == "tool"

    def test_valid_tool_config(self):
        """Valid tool config should pass."""
        config = {"tool": "web_search", "version": "1.0"}
        errors = validate_node_config("tool", config)
        assert len(errors) == 0


class TestMergeNodeSchema:
    """Tests for merge node config validation."""

    def test_empty_config_valid(self):
        """Merge node has no required fields."""
        errors = validate_node_config("merge", {})
        assert len(errors) == 0

    def test_valid_merge_strategies(self):
        """Valid merge strategies should pass."""
        for strategy in ["last_write_wins", "namespaced"]:
            config = {"merge_strategy": strategy}
            errors = validate_node_config("merge", config)
            assert len(errors) == 0, f"Strategy {strategy} should be valid"

    def test_invalid_merge_strategy(self):
        """Invalid merge strategy should fail."""
        config = {"merge_strategy": "first_wins"}
        errors = validate_node_config("merge", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "merge_strategy"


class TestBranchNodeSchema:
    """Tests for branch node config validation."""

    def test_empty_config_valid(self):
        """Branch node has no required fields."""
        errors = validate_node_config("branch", {})
        assert len(errors) == 0

    def test_condition_optional(self):
        """Condition is optional."""
        config = {"condition": "data.value > 10"}
        errors = validate_node_config("branch", config)
        assert len(errors) == 0


class TestSubgraphNodeSchema:
    """Tests for subgraph node config validation."""

    def test_empty_config_valid(self):
        """Subgraph node has no required fields."""
        errors = validate_node_config("subgraph", {})
        assert len(errors) == 0

    def test_valid_full_config(self):
        """Valid subgraph config should pass."""
        config = {
            "graph_id": "abc123",
            "graph_version": 1,
            "input_mapping": {"input": "data.value"},
            "output_mapping": {"result": "output.data"},
        }
        errors = validate_node_config("subgraph", config)
        assert len(errors) == 0


class TestHumanGateNodeSchema:
    """Tests for human gate node config validation."""

    def test_empty_config_valid(self):
        """Human gate has no required fields."""
        errors = validate_node_config("human_gate", {})
        assert len(errors) == 0

    def test_timeout_must_be_positive(self):
        """Timeout must be at least 0."""
        config = {"timeout_seconds": -1}
        errors = validate_node_config("human_gate", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "timeout_seconds"


class TestOutputNodeSchema:
    """Tests for output node config validation."""

    def test_empty_config_valid(self):
        """Output node has no required fields."""
        errors = validate_node_config("output", {})
        assert len(errors) == 0

    def test_output_mapping_optional(self):
        """Output mapping is optional."""
        config = {"output_mapping": {"result": "data.final"}}
        errors = validate_node_config("output", config)
        assert len(errors) == 0


class TestTypeValidation:
    """Tests for type checking in validation."""

    def test_string_type_check(self):
        """Non-string where string expected should fail."""
        config = {"prompt_template": 123}
        errors = validate_node_config("prompt", config)
        assert len(errors) == 1
        assert "string" in errors[0]["message"]

    def test_integer_type_check(self):
        """Non-integer where integer expected should fail."""
        config = {"action": "set", "ttl_seconds": "not a number"}
        errors = validate_node_config("memory", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "ttl_seconds"

    def test_boolean_type_check(self):
        """Non-boolean where boolean expected should fail."""
        config = {"auto_approve": "yes"}
        errors = validate_node_config("human_gate", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "auto_approve"

    def test_array_type_check(self):
        """Non-array where array expected should fail."""
        config = {"required_fields": "field1,field2"}
        errors = validate_node_config("human_gate", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "required_fields"

    def test_object_type_check(self):
        """Non-object where object expected should fail."""
        config = {"url": "https://example.com", "headers": "Content-Type: json"}
        errors = validate_node_config("http", config)
        assert len(errors) == 1
        assert errors[0]["field"] == "headers"
