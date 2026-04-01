"""Marketplace API serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

SEMVER_REGEX = r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"


class MarketplaceInstallSerializer(serializers.Serializer[Any]):
    version = serializers.RegexField(regex=SEMVER_REGEX, required=False)


class MarketplaceReleaseCreateSerializer(serializers.Serializer[Any]):
    PACKAGE_KIND_CHOICES = [
        "template_http",
        "template_prompt",
        "runtime_tool",
        "runtime_transform",
    ]

    package_slug = serializers.SlugField(max_length=100)
    package_name = serializers.CharField(required=False, allow_blank=False, max_length=120)
    package_summary = serializers.CharField(required=False, allow_blank=True)
    package_category = serializers.ChoiceField(
        choices=["communication", "productivity", "crm", "storage", "developer", "other"],
        required=False,
    )
    package_icon = serializers.CharField(required=False, allow_blank=True, max_length=32)
    version = serializers.RegexField(regex=SEMVER_REGEX)
    changelog = serializers.CharField(required=False, allow_blank=True)
    package_kind = serializers.ChoiceField(choices=PACKAGE_KIND_CHOICES, required=False)
    execution_node_type = serializers.ChoiceField(choices=["http", "prompt", "tool", "transform"])
    ui_schema = serializers.JSONField(required=False)
    config_schema = serializers.JSONField(required=False)
    config_defaults = serializers.JSONField(required=False)
    runtime_manifest = serializers.JSONField(required=False, allow_null=True)
    manifest_version = serializers.IntegerField(required=False, min_value=1, default=1)
    cloud_allowed = serializers.BooleanField(required=False, default=True)
    review_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_ui_schema(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("ui_schema must be an object.")
        return value

    def validate_config_schema(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_schema must be an object.")
        return value

    def validate_config_defaults(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_defaults must be an object.")
        return value

    def validate_runtime_manifest(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise serializers.ValidationError("runtime_manifest must be an object.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        package_kind = attrs.get("package_kind")
        execution_node_type = attrs["execution_node_type"]
        if not package_kind:
            package_kind = self._infer_package_kind(execution_node_type)
            attrs["package_kind"] = package_kind

        runtime_manifest = attrs.get("runtime_manifest")
        config_defaults = attrs.get("config_defaults") or {}
        cloud_allowed = bool(attrs.get("cloud_allowed", True))

        expected_execution_type = {
            "template_http": "http",
            "template_prompt": "prompt",
            "runtime_tool": "tool",
            "runtime_transform": "transform",
        }[package_kind]

        if execution_node_type != expected_execution_type:
            raise serializers.ValidationError(
                {
                    "execution_node_type": [
                        f"execution_node_type must be '{expected_execution_type}' for package_kind '{package_kind}'."
                    ]
                }
            )

        if package_kind.startswith("template_"):
            if runtime_manifest:
                raise serializers.ValidationError(
                    {"runtime_manifest": ["Template releases cannot declare runtime_manifest."]}
                )
            return attrs

        if not runtime_manifest:
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime releases must declare runtime_manifest."]}
            )

        if package_kind == "runtime_tool":
            self._validate_runtime_tool_manifest(
                runtime_manifest, attrs["version"], config_defaults
            )
            manifest_kind = str(runtime_manifest.get("kind") or "").strip().lower()
            if manifest_kind == "exec" and cloud_allowed:
                raise serializers.ValidationError(
                    {"cloud_allowed": ["Exec-backed runtime tools cannot be marked cloud_allowed."]}
                )
        elif package_kind == "runtime_transform":
            self._validate_runtime_transform_manifest(runtime_manifest, attrs["version"])

        return attrs

    @staticmethod
    def _infer_package_kind(execution_node_type: str) -> str:
        return {
            "http": "template_http",
            "prompt": "template_prompt",
            "tool": "runtime_tool",
            "transform": "runtime_transform",
        }[execution_node_type]

    @staticmethod
    def _validate_runtime_tool_manifest(
        runtime_manifest: dict[str, Any],
        release_version: str,
        config_defaults: dict[str, Any],
    ) -> None:
        name = str(runtime_manifest.get("name") or "").strip()
        kind = str(runtime_manifest.get("kind") or "").strip().lower()
        if not name:
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime tool manifest requires a non-empty name."]}
            )
        if kind not in {"http", "exec"}:
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime tool manifest kind must be 'http' or 'exec'."]}
            )

        manifest_version = str(runtime_manifest.get("version") or "").strip()
        if manifest_version and manifest_version != release_version:
            raise serializers.ValidationError(
                {"runtime_manifest": ["runtime_manifest.version must match the release version."]}
            )

        input_schema = runtime_manifest.get("input_schema")
        if not isinstance(input_schema, dict):
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime tool manifests require input_schema."]}
            )
        output_schema = runtime_manifest.get("output_schema")
        if output_schema is not None and not isinstance(output_schema, dict):
            raise serializers.ValidationError(
                {"runtime_manifest": ["runtime_manifest.output_schema must be an object."]}
            )

        if kind == "http":
            http_config = runtime_manifest.get("http")
            if not isinstance(http_config, dict):
                raise serializers.ValidationError(
                    {"runtime_manifest": ["HTTP runtime tool manifests require an http object."]}
                )
            url = str(http_config.get("url") or "").strip()
            if not url:
                raise serializers.ValidationError(
                    {"runtime_manifest": ["HTTP runtime tool manifests require http.url."]}
                )

        if kind == "exec":
            exec_config = runtime_manifest.get("exec")
            if not isinstance(exec_config, dict):
                raise serializers.ValidationError(
                    {"runtime_manifest": ["Exec runtime tool manifests require an exec object."]}
                )
            command = str(exec_config.get("command") or "").strip()
            if not command:
                raise serializers.ValidationError(
                    {"runtime_manifest": ["Exec runtime tool manifests require exec.command."]}
                )

        tool_name = str(config_defaults.get("tool") or "").strip()
        if tool_name and tool_name != name:
            raise serializers.ValidationError(
                {"config_defaults": ["config_defaults.tool must match runtime_manifest.name."]}
            )

    @staticmethod
    def _validate_runtime_transform_manifest(
        runtime_manifest: dict[str, Any],
        release_version: str,
    ) -> None:
        name = str(runtime_manifest.get("name") or "").strip()
        kind = str(runtime_manifest.get("kind") or "").strip().lower()
        if not name:
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime transform manifest requires a non-empty name."]}
            )
        if kind != "transform":
            raise serializers.ValidationError(
                {"runtime_manifest": ["Runtime transform manifests must use kind 'transform'."]}
            )

        manifest_version = str(runtime_manifest.get("version") or "").strip()
        if manifest_version and manifest_version != release_version:
            raise serializers.ValidationError(
                {"runtime_manifest": ["runtime_manifest.version must match the release version."]}
            )


class MarketplaceReleaseReviewSerializer(serializers.Serializer[Any]):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    review_notes = serializers.CharField(required=False, allow_blank=True)
