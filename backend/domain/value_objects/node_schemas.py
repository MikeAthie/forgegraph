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

AGENT_NODE_SCHEMA = {
    "instructions": {"type": "string", "required": False},
    "system_prompt": {"type": "string", "required": False},
    "provider": {"type": "string", "required": False, "min_length": 1},
    "credential_id": {"type": "string", "required": False, "min_length": 1},
    "model": {"type": "string", "required": True, "min_length": 1},
    "tools": {"type": "array", "required": True, "min_items": 1, "items_type": "string"},
    "max_steps": {"type": "integer", "min": 1, "required": False},
    "max_tool_calls": {"type": "integer", "min": 1, "required": False},
    "max_tokens": {"type": "integer", "min": 1, "required": False},
    "temperature": {"type": "number", "min": 0, "max": 2, "required": False},
    "observation_context_paths": {
        "type": "array",
        "required": False,
        "items_type": "string",
    },
    "approval_required_tools": {
        "type": "array",
        "required": False,
        "items_type": "string",
    },
    "stop_condition": {"type": "string", "required": False, "enum": ["final_answer"]},
}

PROMPT_NODE_SCHEMA = {
    "prompt_template": {"type": "string", "required": False},
    "prompt_id": {"type": "string", "required": False},
    "system_prompt": {"type": "string", "required": False},
    "provider": {"type": "string", "required": False},
    "credential_id": {"type": "string", "required": False},
    "model": {"type": "string", "required": False},
    "temperature": {"type": "number", "min": 0, "max": 2, "required": False},
    "max_tokens": {"type": "integer", "min": 1, "required": False},
    "observation_context_paths": {
        "type": "array",
        "required": False,
        "items_type": "string",
    },
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
    "provider": {"type": "string", "required": False},
    "credential_id": {"type": "string", "required": False},
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

OBSERVATION_SAVE_NODE_SCHEMA = {
    "observation_id": {"type": "string", "required": False, "min_length": 1},
    "type": {"type": "string", "required": True, "min_length": 1},
    "scope": {
        "type": "string",
        "required": True,
        "enum": ["graph", "run", "session"],
    },
    "title": {"type": "string", "required": False},
    "title_path": {"type": "string", "required": False, "min_length": 1},
    "title_template": {"type": "string", "required": False},
    "content": {"type": "string", "required": False},
    "content_path": {"type": "string", "required": False, "min_length": 1},
    "content_template": {"type": "string", "required": False},
    "topic_key": {"type": "string", "required": False},
    "topic_key_path": {"type": "string", "required": False, "min_length": 1},
    "tool_name": {"type": "string", "required": False},
    "tool_name_path": {"type": "string", "required": False, "min_length": 1},
    "agent_id": {"type": "string", "required": False},
    "agent_id_path": {"type": "string", "required": False, "min_length": 1},
    "dedupe": {"type": "boolean", "required": False},
    "update_topic": {"type": "boolean", "required": False},
}

OBSERVATION_SEARCH_NODE_SCHEMA = {
    "scope": {
        "type": "string",
        "required": True,
        "enum": ["graph", "run", "session"],
    },
    "query": {"type": "string", "required": False},
    "query_path": {"type": "string", "required": False, "min_length": 1},
    "query_template": {"type": "string", "required": False},
    "type": {"type": "string", "required": False},
    "topic_key": {"type": "string", "required": False},
    "topic_key_path": {"type": "string", "required": False, "min_length": 1},
    "agent_id": {"type": "string", "required": False},
    "agent_id_path": {"type": "string", "required": False, "min_length": 1},
    "limit": {"type": "integer", "required": False, "min": 1},
    "include_deleted": {"type": "boolean", "required": False},
}

OBSERVATION_CONTEXT_NODE_SCHEMA = {
    "query": {"type": "string", "required": False},
    "query_path": {"type": "string", "required": False, "min_length": 1},
    "query_template": {"type": "string", "required": False},
    "agent_id": {"type": "string", "required": False},
    "agent_id_path": {"type": "string", "required": False, "min_length": 1},
    "limit": {"type": "integer", "required": False, "min": 1},
}

OBSERVATION_TIMELINE_NODE_SCHEMA = {
    "scope": {
        "type": "string",
        "required": True,
        "enum": ["graph", "run", "session"],
    },
    "agent_id": {"type": "string", "required": False},
    "agent_id_path": {"type": "string", "required": False, "min_length": 1},
    "limit": {"type": "integer", "required": False, "min": 1},
    "include_deleted": {"type": "boolean", "required": False},
}

TOOL_NODE_SCHEMA = {
    "tool": {"type": "string", "required": True, "min_length": 1},
    "version": {"type": "string", "required": False},
    "provider": {"type": "string", "required": False},
    "credential_id": {"type": "string", "required": False},
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
    NodeType.AGENT.value: AGENT_NODE_SCHEMA,
    NodeType.PROMPT.value: PROMPT_NODE_SCHEMA,
    NodeType.HTTP.value: HTTP_NODE_SCHEMA,
    NodeType.TRANSFORM.value: TRANSFORM_NODE_SCHEMA,
    NodeType.BRANCH.value: BRANCH_NODE_SCHEMA,
    NodeType.MERGE.value: MERGE_NODE_SCHEMA,
    NodeType.HUMAN_GATE.value: HUMAN_GATE_NODE_SCHEMA,
    NodeType.MEMORY.value: MEMORY_NODE_SCHEMA,
    NodeType.OBSERVATION_SAVE.value: OBSERVATION_SAVE_NODE_SCHEMA,
    NodeType.OBSERVATION_SEARCH.value: OBSERVATION_SEARCH_NODE_SCHEMA,
    NodeType.OBSERVATION_CONTEXT.value: OBSERVATION_CONTEXT_NODE_SCHEMA,
    NodeType.OBSERVATION_TIMELINE.value: OBSERVATION_TIMELINE_NODE_SCHEMA,
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

        # Minimum items validation for arrays
        if field_type == "array" and "min_items" in field_schema:
            if len(value) < field_schema["min_items"]:
                errors.append(
                    {
                        "field": field_name,
                        "message": f"'{field_name}' must contain at least {field_schema['min_items']} item(s)",
                        "suggestion": f"Add at least {field_schema['min_items']} item(s) to '{field_name}'",
                    }
                )

        if field_type == "array" and "items_type" in field_schema:
            expected_item_type = field_schema["items_type"]
            for item in value:
                item_error = _validate_type(field_name, item, {"type": expected_item_type})
                if item_error:
                    errors.append(
                        {
                            "field": field_name,
                            "message": f"All items in '{field_name}' must be {expected_item_type} values",
                            "suggestion": f"Only include {expected_item_type} values in '{field_name}'",
                        }
                    )
                    break

        # Enum validation
        if "enum" in field_schema and value not in field_schema["enum"]:
            errors.append(
                {
                    "field": field_name,
                    "message": f"'{field_name}' must be one of: {', '.join(field_schema['enum'])}",
                    "suggestion": f"Use one of the allowed values: {', '.join(field_schema['enum'])}",
                }
            )

    if node_type == NodeType.PROMPT.value:
        prompt_template = config.get("prompt_template")
        prompt_id = config.get("prompt_id")
        has_prompt_template = isinstance(prompt_template, str) and bool(prompt_template.strip())
        has_prompt_id = isinstance(prompt_id, str) and bool(prompt_id.strip())
        if not has_prompt_template and not has_prompt_id:
            errors.append(
                {
                    "field": "prompt_template",
                    "message": "Prompt node requires either 'prompt_template' or 'prompt_id'",
                    "suggestion": "Set a prompt template directly or reference a prompt by id",
                }
            )

    if node_type == NodeType.AGENT.value:
        tools = config.get("tools")
        if isinstance(tools, list):
            normalized_tools = [
                tool.strip() for tool in tools if isinstance(tool, str) and tool.strip()
            ]

            if len(normalized_tools) != len(tools):
                errors.append(
                    {
                        "field": "tools",
                        "message": "Agent tools must be non-empty strings",
                        "suggestion": "Provide one or more tool names as non-empty strings",
                    }
                )

            approval_required_tools = config.get("approval_required_tools")
            if isinstance(approval_required_tools, list):
                invalid_tools = [
                    tool
                    for tool in approval_required_tools
                    if not isinstance(tool, str) or tool.strip() not in normalized_tools
                ]
                if invalid_tools:
                    errors.append(
                        {
                            "field": "approval_required_tools",
                            "message": "Approval-required tools must be included in 'tools'",
                            "suggestion": "Only require approval for tools already listed in 'tools'",
                        }
                    )

        max_steps = config.get("max_steps")
        max_tool_calls = config.get("max_tool_calls")
        if (
            isinstance(max_steps, int)
            and isinstance(max_tool_calls, int)
            and max_tool_calls > max_steps
        ):
            errors.append(
                {
                    "field": "max_tool_calls",
                    "message": "'max_tool_calls' cannot exceed 'max_steps'",
                    "suggestion": "Set 'max_tool_calls' to a value less than or equal to 'max_steps'",
                }
            )

    if node_type == NodeType.OBSERVATION_SAVE.value:
        _validate_exactly_one_source(
            errors,
            config,
            field="content",
            source_fields=["content", "content_path", "content_template"],
            suggestion="Set exactly one of 'content', 'content_path', or 'content_template'",
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="title",
            source_fields=["title", "title_path", "title_template"],
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="topic_key",
            source_fields=["topic_key", "topic_key_path"],
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="tool_name",
            source_fields=["tool_name", "tool_name_path"],
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="agent_id",
            source_fields=["agent_id", "agent_id_path"],
        )

        if config.get("update_topic") is True and not _has_any_value(
            config, ["topic_key", "topic_key_path"]
        ):
            errors.append(
                {
                    "field": "topic_key",
                    "message": "'update_topic' requires 'topic_key' or 'topic_key_path'",
                    "suggestion": "Set a topic key source before enabling 'update_topic'",
                }
            )

    if node_type == NodeType.OBSERVATION_SEARCH.value:
        _validate_exactly_one_source(
            errors,
            config,
            field="query",
            source_fields=["query", "query_path", "query_template"],
            suggestion="Set exactly one of 'query', 'query_path', or 'query_template'",
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="topic_key",
            source_fields=["topic_key", "topic_key_path"],
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="agent_id",
            source_fields=["agent_id", "agent_id_path"],
        )

    if node_type == NodeType.OBSERVATION_CONTEXT.value:
        _validate_exactly_one_source(
            errors,
            config,
            field="query",
            source_fields=["query", "query_path", "query_template"],
            suggestion="Set exactly one of 'query', 'query_path', or 'query_template'",
        )
        _validate_at_most_one_source(
            errors,
            config,
            field="agent_id",
            source_fields=["agent_id", "agent_id_path"],
        )

    if node_type == NodeType.OBSERVATION_TIMELINE.value:
        _validate_at_most_one_source(
            errors,
            config,
            field="agent_id",
            source_fields=["agent_id", "agent_id_path"],
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


def _has_any_value(config: dict[str, Any], source_fields: list[str]) -> bool:
    return any(_has_value(config.get(field_name)) for field_name in source_fields)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _validate_exactly_one_source(
    errors: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    field: str,
    source_fields: list[str],
    suggestion: str,
) -> None:
    populated_fields = [
        field_name for field_name in source_fields if _has_value(config.get(field_name))
    ]
    if len(populated_fields) == 1:
        return
    if not populated_fields:
        errors.append(
            {
                "field": field,
                "message": f"'{field}' requires one configured source",
                "suggestion": suggestion,
            }
        )
        return
    errors.append(
        {
            "field": field,
            "message": f"Only one of {', '.join(source_fields)} may be set",
            "suggestion": suggestion,
        }
    )


def _validate_at_most_one_source(
    errors: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    field: str,
    source_fields: list[str],
) -> None:
    populated_fields = [
        field_name for field_name in source_fields if _has_value(config.get(field_name))
    ]
    if len(populated_fields) <= 1:
        return
    errors.append(
        {
            "field": field,
            "message": f"Only one of {', '.join(source_fields)} may be set",
            "suggestion": f"Choose a single source for '{field}'",
        }
    )
