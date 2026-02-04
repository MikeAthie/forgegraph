"""
Node configuration schemas.

Defines JSON Schema-like validation rules for each node type's config.
Used for strict mode validation in GraphValidator.

Clean Architecture: Enterprise Business Rules layer.
"""

from typing import Any

from domain.value_objects.node_types import NodeType

# Schema definitions for each node type
# Format: {field_name: {required: bool, type: str, min_length?: int, ...}}

PROMPT_NODE_SCHEMA = {
    "prompt_template": {"type": "string", "required": False},
    "prompt_id": {"type": "string", "required": False},
    "system_prompt": {"type": "string", "required": False},
    "provider": {"type": "string", "required": False},
    "credential_id": {"type": "string", "required": False},
    "model": {"type": "string", "required": False},
    "temperature": {"type": "number", "min": 0, "max": 2, "required": False},
    "max_tokens": {"type": "integer", "min": 1, "required": False},
    # Agent fields
    "role": {"type": "string", "required": False},
    "job_description": {"type": "string", "required": False},
    "examples": {"type": "array", "required": False},
    "notes": {"type": "string", "required": False},
}

HTTP_NODE_SCHEMA = {
    "url": {"type": "string", "required": True, "min_length": 1},
    "method": {
        "type": "string",
        "required": False,
        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
    },
    "headers": {"type": "object", "required": False},
    "body": {"type": "string", "required": False},
    "output_key": {"type": "string", "required": False},
}

TRANSFORM_NODE_SCHEMA = {
    "expression": {"type": "string", "required": True, "min_length": 1},
    "output_key": {"type": "string", "required": False},
}

BRANCH_NODE_SCHEMA = {
    "condition": {"type": "string", "required": False},
}

MERGE_NODE_SCHEMA = {
    "merge_strategy": {
        "type": "string",
        "required": False,
        "enum": ["last_write_wins", "namespaced"],
    },
}

HUMAN_GATE_NODE_SCHEMA = {
    "prompt_message": {"type": "string", "required": False},
    "required_fields": {"type": "array", "required": False},
    "auto_approve": {"type": "boolean", "required": False},
    "timeout_seconds": {"type": "integer", "min": 0, "required": False},
}

MEMORY_NODE_SCHEMA = {
    "action": {
        "type": "string",
        "required": True,
        "enum": ["get", "set", "delete"],
    },
    "key": {"type": "string", "required": False},
    "namespace": {"type": "string", "required": False},
    "value": {"type": "any", "required": False},
    "value_path": {"type": "string", "required": False},
    "ttl_seconds": {"type": "integer", "min": 0, "required": False},
}

TOOL_NODE_SCHEMA = {
    "tool": {"type": "string", "required": True, "min_length": 1},
    "version": {"type": "string", "required": False},
    "input": {"type": "any", "required": False},
    "input_path": {"type": "string", "required": False},
    "config": {"type": "object", "required": False},
}

SUBGRAPH_NODE_SCHEMA = {
    "graph_id": {"type": "string", "required": False},
    "graph_version": {"type": "integer", "required": False},
    "graph_json": {"type": "object", "required": False},
    "input_mapping": {"type": "object", "required": False},
    "output_mapping": {"type": "object", "required": False},
}

OUTPUT_NODE_SCHEMA = {
    "output_mapping": {"type": "object", "required": False},
}

# Registry of node type -> schema
NODE_SCHEMAS: dict[str, dict[str, Any]] = {
    NodeType.PROMPT.value: PROMPT_NODE_SCHEMA,
    NodeType.HTTP.value: HTTP_NODE_SCHEMA,
    NodeType.TRANSFORM.value: TRANSFORM_NODE_SCHEMA,
    NodeType.BRANCH.value: BRANCH_NODE_SCHEMA,
    NodeType.MERGE.value: MERGE_NODE_SCHEMA,
    NodeType.HUMAN_GATE.value: HUMAN_GATE_NODE_SCHEMA,
    NodeType.MEMORY.value: MEMORY_NODE_SCHEMA,
    NodeType.TOOL.value: TOOL_NODE_SCHEMA,
    NodeType.SUBGRAPH.value: SUBGRAPH_NODE_SCHEMA,
    NodeType.OUTPUT.value: OUTPUT_NODE_SCHEMA,
}


def get_schema_for_type(node_type: str) -> dict[str, Any] | None:
    """Get the schema for a node type."""
    return NODE_SCHEMAS.get(node_type)


def validate_node_config(node_type: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Validate a node's config against its schema.

    Returns a list of validation errors, empty if valid.
    """
    schema = get_schema_for_type(node_type)
    if not schema:
        return []  # Unknown type, skip validation

    errors = []

    for field_name, field_schema in schema.items():
        value = config.get(field_name)
        is_required = field_schema.get("required", False)
        field_type = field_schema.get("type", "any")

        # Check required fields
        if is_required and value is None:
            errors.append(
                {
                    "field": field_name,
                    "message": f"Required field '{field_name}' is missing",
                    "suggestion": f"Add a value for '{field_name}'",
                }
            )
            continue

        # Skip validation if value is not present and not required
        if value is None:
            continue

        # Type validation
        type_error = _validate_type(field_name, value, field_schema)
        if type_error:
            errors.append(type_error)
            continue

        # Min/max validation for numbers
        if field_type in ("number", "integer"):
            if "min" in field_schema and value < field_schema["min"]:
                errors.append(
                    {
                        "field": field_name,
                        "message": f"'{field_name}' must be at least {field_schema['min']}",
                        "suggestion": f"Set '{field_name}' to {field_schema['min']} or higher",
                    }
                )
            if "max" in field_schema and value > field_schema["max"]:
                errors.append(
                    {
                        "field": field_name,
                        "message": f"'{field_name}' must be at most {field_schema['max']}",
                        "suggestion": f"Set '{field_name}' to {field_schema['max']} or lower",
                    }
                )

        # Min length validation for strings
        if field_type == "string" and "min_length" in field_schema:
            if len(value) < field_schema["min_length"]:
                errors.append(
                    {
                        "field": field_name,
                        "message": f"'{field_name}' is too short",
                        "suggestion": f"Provide a longer value for '{field_name}'",
                    }
                )

        # Enum validation
        if "enum" in field_schema and value not in field_schema["enum"]:
            errors.append(
                {
                    "field": field_name,
                    "message": f"'{field_name}' must be one of: {', '.join(field_schema['enum'])}",
                    "suggestion": f"Use one of the allowed values: {', '.join(field_schema['enum'])}",
                }
            )

    return errors


def _validate_type(field_name: str, value: Any, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a value's type against the schema."""
    expected_type = schema.get("type", "any")

    if expected_type == "any":
        return None

    type_checks = {
        "string": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }

    check_fn = type_checks.get(expected_type)
    if check_fn and not check_fn(value):
        return {
            "field": field_name,
            "message": f"'{field_name}' must be a {expected_type}",
            "suggestion": f"Provide a {expected_type} value for '{field_name}'",
        }

    return None
