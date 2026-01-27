"""
JSON schema validation helpers.

Clean Architecture: Application Services layer.
"""

from __future__ import annotations

from typing import Any

from jsonschema import exceptions as jsonschema_exceptions
from jsonschema import validators


def extract_schema_metadata(graph_json: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    if not isinstance(graph_json, dict):
        return None, None, "warn"

    metadata = graph_json.get("metadata")
    if not isinstance(metadata, dict):
        return None, None, "warn"

    input_schema = metadata.get("input_schema")
    if not isinstance(input_schema, dict):
        input_schema = None

    output_schema = metadata.get("output_schema")
    if not isinstance(output_schema, dict):
        output_schema = None

    mode_raw = metadata.get("schema_mode") or metadata.get("validation_mode")
    if isinstance(mode_raw, str) and mode_raw.lower() == "strict":
        mode = "strict"
    else:
        mode = "warn"

    return input_schema, output_schema, mode


def validate_json_schema(data: Any, schema: dict[str, Any]) -> list[dict[str, Any]]:
    validator_cls = validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    formatted: list[dict[str, Any]] = []
    for err in errors:
        formatted.append(
            {
                "message": err.message,
                "path": list(err.path),
                "schema_path": list(err.schema_path),
            }
        )
    return formatted


SchemaError = jsonschema_exceptions.SchemaError
