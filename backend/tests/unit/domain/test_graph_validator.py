"""
Unit tests for GraphValidator domain service.

Tests graph validation including start/output node requirements,
sentinel edge validation, and structural checks.
"""

from domain.services.graph_validator import GraphValidator


class TestGraphValidatorStartOutputRequirements:
    """Tests for start and output node validation."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_no_start_node_error(self):
        """Graph without START edges should fail validation."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert len(errors) == 1
        assert errors[0]["type"] == "no_start_node"
        assert "start node" in errors[0]["message"].lower()

    def test_no_output_node_error(self):
        """Graph without output nodes should fail validation."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "transform", "name": "Transform"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert len(errors) == 1
        assert errors[0]["type"] == "no_output_node"
        assert "output node" in errors[0]["message"].lower()

    def test_missing_both_start_and_output(self):
        """Graph missing both start and output should return both errors."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
            ],
            "edges": [],
        }

        errors = self.validator.validate(graph_json)

        error_types = [e["type"] for e in errors]
        assert "no_start_node" in error_types
        assert "no_output_node" in error_types

    def test_valid_graph_with_start_and_output(self):
        """Valid graph with start and output should pass validation."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                {"id": "end-node2", "from": "node2", "to": "END"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert len(errors) == 0


class TestGraphValidatorSentinelEdges:
    """Tests for START/END sentinel edge validation."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_valid_start_edge(self):
        """START edge to valid node should pass."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json)

        # Only no_output_node error should be present (no END edge)
        # Actually with the output node, it should pass
        assert len(errors) == 0

    def test_invalid_start_to_end(self):
        """START edge directly to END should fail."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-end", "from": "START", "to": "END"},
                {"id": "start-node1", "from": "START", "to": "node1"},
            ],
        }

        errors = self.validator.validate(graph_json)

        error_types = [e["type"] for e in errors]
        assert "edge_invalid_to" in error_types

    def test_invalid_end_from_start(self):
        """END edge from START should fail."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "bad-edge", "from": "START", "to": "END"},
                {"id": "start-node1", "from": "START", "to": "node1"},
            ],
        }

        errors = self.validator.validate(graph_json)

        # Should have invalid edge errors
        assert any(e["type"] == "edge_invalid_to" for e in errors)

    def test_valid_end_edge(self):
        """END edge from valid node should pass."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                {"id": "end-node2", "from": "node2", "to": "END"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert len(errors) == 0


class TestGraphValidatorNodeValidation:
    """Tests for node-level validation."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_reserved_node_id_start(self):
        """Using START as node ID should fail."""
        graph_json = {
            "nodes": [
                {"id": "START", "type": "prompt", "name": "Bad Node"},
            ],
            "edges": [],
        }

        errors = self.validator.validate(graph_json)

        assert any(e["type"] == "reserved_node_id" for e in errors)

    def test_reserved_node_id_end(self):
        """Using END as node ID should fail."""
        graph_json = {
            "nodes": [
                {"id": "END", "type": "prompt", "name": "Bad Node"},
            ],
            "edges": [],
        }

        errors = self.validator.validate(graph_json)

        assert any(e["type"] == "reserved_node_id" for e in errors)

    def test_duplicate_node_ids(self):
        """Duplicate node IDs should fail."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node1", "type": "output", "name": "Output"},
            ],
            "edges": [],
        }

        errors = self.validator.validate(graph_json)

        assert any(e["type"] == "duplicate_node_id" for e in errors)

    def test_invalid_node_type(self):
        """Invalid node type should fail."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "invalid_type", "name": "Bad Node"},
            ],
            "edges": [],
        }

        errors = self.validator.validate(graph_json)

        assert any(e["type"] == "invalid_node_type" for e in errors)


class TestGraphValidatorCycleDetection:
    """Tests for cycle detection."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_simple_cycle_detected(self):
        """Simple cycle should be detected."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "transform", "name": "Transform"},
                {"id": "node3", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                {"id": "e2", "from": "node2", "to": "node1"},  # Cycle!
                {"id": "e3", "from": "node2", "to": "node3"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert any(e["type"] == "cycle_detected" for e in errors)

    def test_dag_no_cycle(self):
        """Valid DAG should not report cycles."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "transform", "name": "Transform"},
                {"id": "node3", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                {"id": "e2", "from": "node2", "to": "node3"},
            ],
        }

        errors = self.validator.validate(graph_json)

        assert not any(e["type"] == "cycle_detected" for e in errors)


class TestGraphValidatorDisconnectedNodes:
    """Tests for disconnected node detection."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_disconnected_node_warning(self):
        """Completely disconnected node should produce a warning."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Connected"},
                {"id": "node2", "type": "transform", "name": "Disconnected"},
                {"id": "node3", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node3"},
            ],
        }

        result = self.validator.validate(graph_json)

        # Should have a warning for node2
        warnings = [r for r in result if r.get("severity") == "warning"]
        assert len(warnings) == 1
        assert warnings[0]["type"] == "disconnected_node"
        assert warnings[0]["node_id"] == "node2"

    def test_no_disconnected_nodes_warning(self):
        """Fully connected graph should not have disconnected warnings."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt 1"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                {"id": "end-node2", "from": "node2", "to": "END"},
            ],
        }

        result = self.validator.validate(graph_json)

        warnings = [r for r in result if r.get("severity") == "warning"]
        assert len(warnings) == 0

    def test_node_with_only_incoming_is_connected(self):
        """Node with only incoming edges is connected (terminal node)."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "Prompt"},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
                # node2 has only incoming, no outgoing (terminal)
            ],
        }

        result = self.validator.validate(graph_json)

        # Warnings check - node2 should not be flagged as disconnected
        disconnected = [r for r in result if r.get("type") == "disconnected_node"]
        assert not any(d["node_id"] == "node2" for d in disconnected)


class TestGraphValidatorStrictMode:
    """Tests for strict mode validation."""

    def setup_method(self):
        self.validator = GraphValidator()

    def test_strict_mode_validates_http_node_url_required(self):
        """Strict mode should validate HTTP node requires URL."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "http", "name": "HTTP", "config": {}},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        # Should have config error for missing url
        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "url"

    def test_strict_mode_validates_transform_expression_required(self):
        """Strict mode should validate transform node requires expression."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "transform", "name": "Transform", "config": {}},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "expression"

    def test_strict_mode_validates_tool_tool_required(self):
        """Strict mode should validate tool node requires tool field."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "tool", "name": "Tool", "config": {}},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "tool"

    def test_strict_mode_validates_memory_action_required(self):
        """Strict mode should validate memory node requires action field."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "memory", "name": "Memory", "config": {}},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "action"

    def test_non_strict_mode_skips_config_validation(self):
        """Non-strict mode should not validate node configs."""
        graph_json = {
            "nodes": [
                {"id": "node1", "type": "http", "name": "HTTP", "config": {}},
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=False)

        # Should have no config errors in non-strict mode
        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 0

    def test_strict_mode_validates_temperature_range(self):
        """Strict mode should validate temperature is within range."""
        graph_json = {
            "nodes": [
                {
                    "id": "node1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {"temperature": 3.0},  # Invalid: max is 2
                },
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "temperature"

    def test_strict_mode_validates_enum_values(self):
        """Strict mode should validate enum field values."""
        graph_json = {
            "nodes": [
                {
                    "id": "node1",
                    "type": "http",
                    "name": "HTTP",
                    "config": {"url": "https://example.com", "method": "INVALID"},
                },
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "method"

    def test_strict_mode_valid_config_passes(self):
        """Valid config should pass strict mode validation."""
        graph_json = {
            "nodes": [
                {
                    "id": "node1",
                    "type": "http",
                    "name": "HTTP",
                    "config": {"url": "https://api.example.com", "method": "GET"},
                },
                {"id": "node2", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "start-node1", "from": "START", "to": "node1"},
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        errors = self.validator.validate(graph_json, strict=True)

        config_errors = [e for e in errors if e.get("type") == "invalid_node_config"]
        assert len(config_errors) == 0
