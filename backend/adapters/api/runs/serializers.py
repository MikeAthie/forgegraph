"""
Runs API serializers (stub for Phase 4).

Clean Architecture: Interface Adapters layer.
"""

from typing import Any

from rest_framework import serializers

RUN_STATUS_CHOICES = ["pending", "running", "paused", "succeeded", "failed", "canceled"]
NODE_RUN_STATUS_CHOICES = ["pending", "running", "waiting", "succeeded", "failed", "skipped"]


class RunStartSerializer(serializers.Serializer[Any]):
    """Serializer for starting a run."""

    graph_version_id = serializers.UUIDField()
    input_json = serializers.JSONField(required=False, default=dict)
    thread_id = serializers.UUIDField(required=False, allow_null=True)


class RunInvokeSerializer(serializers.Serializer[Any]):
    """Serializer for invoking a threaded run."""

    thread_id = serializers.UUIDField()
    input_json = serializers.JSONField(required=False, default=dict)


class RunResumeSerializer(serializers.Serializer[Any]):
    """Serializer for resuming a run."""

    node_id = serializers.CharField()
    input_json = serializers.JSONField(required=False, default=dict)


class RunReplaySerializer(serializers.Serializer[Any]):
    """Serializer for replaying a run from a checkpoint."""

    node_id = serializers.CharField(required=False, allow_blank=True)


class RunListSerializer(serializers.Serializer[Any]):
    """Serializer for run list output."""

    id = serializers.UUIDField(read_only=True)
    thread_id = serializers.UUIDField(read_only=True, allow_null=True)
    graph_id = serializers.UUIDField(read_only=True)
    graph_name = serializers.CharField(read_only=True)
    graph_version_id = serializers.UUIDField(read_only=True)
    graph_version = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    queue_status = serializers.CharField(read_only=True, allow_null=True)
    queue_attempts = serializers.IntegerField(read_only=True, allow_null=True)
    queue_available_at = serializers.DateTimeField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)


class RunDetailSerializer(serializers.Serializer[Any]):
    """Serializer for run detail output."""

    id = serializers.UUIDField(read_only=True)
    owner_id = serializers.UUIDField(read_only=True)
    thread_id = serializers.UUIDField(read_only=True, allow_null=True)
    graph_id = serializers.UUIDField(read_only=True)
    graph_name = serializers.CharField(read_only=True)
    graph_version_id = serializers.UUIDField(read_only=True)
    graph_version = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    queue_status = serializers.CharField(read_only=True, allow_null=True)
    queue_attempts = serializers.IntegerField(read_only=True, allow_null=True)
    queue_available_at = serializers.DateTimeField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    input_json = serializers.JSONField(read_only=True)
    output_json = serializers.JSONField(read_only=True, allow_null=True)
    error_message = serializers.CharField(read_only=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)
    # Human Gate pause fields
    paused_node_id = serializers.CharField(read_only=True, allow_null=True)
    pause_payload = serializers.JSONField(read_only=True, allow_null=True)


class NodeRunSerializer(serializers.Serializer[Any]):
    """Serializer for node run output."""

    id = serializers.UUIDField(read_only=True)
    node_id = serializers.CharField(read_only=True)
    node_type = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    attempt = serializers.IntegerField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)
    input_json = serializers.JSONField(read_only=True)
    output_json = serializers.JSONField(read_only=True, allow_null=True)
    error_json = serializers.JSONField(read_only=True, allow_null=True)


class RunDetailWithNodeRunsSerializer(RunDetailSerializer):
    """Run detail output including nested node run objects."""

    node_runs = NodeRunSerializer(many=True, read_only=True)


class RunDeltaBroadcastSerializer(serializers.Serializer[Any]):
    """Minimal run payload for WebSocket broadcast events."""

    id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)
    output_json = serializers.JSONField(read_only=True, allow_null=True)
    error_message = serializers.CharField(read_only=True)


class NodeRunDeltaSerializer(serializers.Serializer[Any]):
    """NodeRun delta payload sent by the engine/control-plane."""

    node_id = serializers.CharField()
    node_type = serializers.CharField()
    status = serializers.ChoiceField(choices=NODE_RUN_STATUS_CHOICES)
    attempt = serializers.IntegerField(required=False, default=1, min_value=1)
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    input_json = serializers.JSONField(required=False)
    output_json = serializers.JSONField(required=False, allow_null=True)
    error_json = serializers.JSONField(required=False, allow_null=True)


class RunUpdateDeltaSerializer(serializers.Serializer[Any]):
    """Run delta payload sent by the engine/control-plane."""

    status = serializers.ChoiceField(choices=RUN_STATUS_CHOICES, required=False)
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    output_json = serializers.JSONField(required=False, allow_null=True)
    error_message = serializers.CharField(required=False, allow_blank=True)

    # Human gate pause fields
    paused_node_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pause_state_json = serializers.JSONField(required=False, allow_null=True)
    pause_payload = serializers.JSONField(required=False, allow_null=True)  # From engine event


class RunEventSerializer(serializers.Serializer[Any]):
    """Run event wrapper used by the broadcast endpoint."""

    event_type = serializers.ChoiceField(
        choices=["node_run.updated", "run.updated", "run.schema_validation"]
    )
    node_run = NodeRunDeltaSerializer(required=False)
    run = RunUpdateDeltaSerializer(required=False)
    payload = serializers.JSONField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        event_type = attrs.get("event_type")

        if event_type == "node_run.updated" and "node_run" not in attrs:
            raise serializers.ValidationError(
                {"node_run": ["node_run is required for node_run.updated"]}
            )
        if event_type == "run.updated" and "run" not in attrs:
            raise serializers.ValidationError({"run": ["run is required for run.updated"]})
        if event_type == "run.schema_validation" and "payload" not in attrs:
            raise serializers.ValidationError(
                {"payload": ["payload is required for run.schema_validation"]}
            )

        return attrs


class EngineExecutionEventSerializer(serializers.Serializer[Any]):
    """Serializer for execution events emitted by the engine."""

    event_id = serializers.CharField(required=False, allow_blank=True)
    version = serializers.IntegerField(required=False)
    type = serializers.CharField()
    run_id = serializers.UUIDField()
    tenant_id = serializers.UUIDField()
    node_id = serializers.CharField(required=False, allow_blank=True)
    node_type = serializers.CharField(required=False, allow_blank=True)
    node_name = serializers.CharField(required=False, allow_blank=True)
    attempt = serializers.IntegerField(required=False, min_value=1)
    input = serializers.JSONField(required=False)
    output = serializers.JSONField(required=False)
    error = serializers.CharField(required=False, allow_blank=True)
    timestamp = serializers.IntegerField(required=False)
    duration_ms = serializers.IntegerField(required=False)
