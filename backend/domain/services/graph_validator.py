"""
Graph validation domain service.

Clean Architecture: Enterprise Business Rules layer.
"""

from collections import defaultdict
from typing import Any

from domain.exceptions import (
    GraphValidationError,
)
from domain.value_objects.node_types import NodeType


class GraphValidator:
    """Validates graph structure and semantics."""

    START_NODE_ID = "START"
    END_NODE_ID = "END"

    def validate(
        self,
        graph_json: dict[str, Any],
        *,
        strict: bool = False,
        require_entry_exit: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Validate a graph JSON structure.

        Returns a list of validation errors. Empty list means valid.
        Raises GraphValidationError for critical structural issues.

        Args:
            graph_json: The graph structure to validate
            strict: If True, also validates node configs against schemas
        """
        errors = []
        warnings = []

        # Check required top-level keys
        if "nodes" not in graph_json:
            errors.append(
                {
                    "type": "missing_key",
                    "key": "nodes",
                    "message": "Graph JSON is missing required 'nodes' array",
                    "suggestion": "Add a 'nodes' array to your graph JSON",
                }
            )
        if "edges" not in graph_json:
            errors.append(
                {
                    "type": "missing_key",
                    "key": "edges",
                    "message": "Graph JSON is missing required 'edges' array",
                    "suggestion": "Add an 'edges' array to your graph JSON",
                }
            )

        if errors:
            raise GraphValidationError("Graph JSON missing required keys", errors=errors)

        nodes = graph_json.get("nodes", [])
        edges = graph_json.get("edges", [])

        # Validate nodes
        node_ids = set()
        for node in nodes:
            node_errors = self._validate_node(node, node_ids)
            errors.extend(node_errors)
            if "id" in node:
                node_ids.add(node["id"])

        # Validate edges
        for edge in edges:
            edge_errors = self._validate_edge(edge, node_ids)
            errors.extend(edge_errors)

        # Check start/output node requirements
        if require_entry_exit and not errors:
            requirement_errors = self._validate_start_output_requirements(nodes, edges)
            errors.extend(requirement_errors)

        # Check for disconnected nodes (warning, not error)
        if not errors:
            disconnected = self._find_disconnected_nodes(nodes, edges)
            warnings.extend(disconnected)

        # Check for cycles (DAG validation)
        if not errors:
            cycle_error = self._check_for_cycles(nodes, edges)
            if cycle_error:
                errors.append(cycle_error)

        # Strict mode: validate node configs against schemas
        if strict and not errors:
            config_errors = self._validate_node_configs(nodes)
            errors.extend(config_errors)

        # Combine errors and warnings
        return errors + warnings

    def validate_or_raise(self, graph_json: dict[str, Any]) -> None:
        """
        Validate a graph and raise GraphValidationError if invalid.
        """
        errors = self.validate(graph_json)
        if errors:
            raise GraphValidationError(
                f"Graph validation failed with {len(errors)} error(s)", errors=errors
            )

    def _validate_node(self, node: dict[str, Any], existing_ids: set[str]) -> list[dict[str, Any]]:
        """Validate a single node."""
        errors = []

        # Check required fields
        if "id" not in node:
            errors.append({"type": "node_missing_id", "node": node})
            return errors

        node_id = node["id"]

        if node_id in {self.START_NODE_ID, self.END_NODE_ID}:
            errors.append({"type": "reserved_node_id", "node_id": node_id})

        if node_id in existing_ids:
            errors.append({"type": "duplicate_node_id", "node_id": node_id})

        if "type" not in node:
            errors.append({"type": "node_missing_type", "node_id": node_id})
        elif not NodeType.is_valid(node["type"]):
            errors.append(
                {"type": "invalid_node_type", "node_id": node_id, "node_type": node["type"]}
            )

        if "name" not in node:
            errors.append({"type": "node_missing_name", "node_id": node_id})

        return errors

    def _validate_edge(self, edge: dict[str, Any], node_ids: set[str]) -> list[dict[str, Any]]:
        """Validate a single edge."""
        errors = []

        if "id" not in edge:
            errors.append({"type": "edge_missing_id", "edge": edge})
            return errors

        edge_id = edge["id"]

        if "from" not in edge:
            errors.append({"type": "edge_missing_from", "edge_id": edge_id})
        else:
            from_node = edge["from"]
            if from_node == self.END_NODE_ID:
                errors.append(
                    {"type": "edge_invalid_from", "edge_id": edge_id, "from_node": from_node}
                )
            elif from_node != self.START_NODE_ID and from_node not in node_ids:
                errors.append(
                    {"type": "edge_invalid_from", "edge_id": edge_id, "from_node": from_node}
                )

        if "to" not in edge:
            errors.append({"type": "edge_missing_to", "edge_id": edge_id})
        else:
            to_node = edge["to"]
            if to_node == self.START_NODE_ID:
                errors.append({"type": "edge_invalid_to", "edge_id": edge_id, "to_node": to_node})
            elif to_node != self.END_NODE_ID and to_node not in node_ids:
                errors.append({"type": "edge_invalid_to", "edge_id": edge_id, "to_node": to_node})

        # Validate START/END sentinel semantics
        from_node = edge.get("from")
        to_node = edge.get("to")
        if from_node == self.START_NODE_ID:
            if (
                to_node == self.END_NODE_ID
                or to_node == self.START_NODE_ID
                or to_node not in node_ids
            ):
                errors.append({"type": "edge_invalid_to", "edge_id": edge_id, "to_node": to_node})
        if to_node == self.END_NODE_ID:
            if (
                from_node == self.START_NODE_ID
                or from_node == self.END_NODE_ID
                or from_node not in node_ids
            ):
                errors.append(
                    {"type": "edge_invalid_from", "edge_id": edge_id, "from_node": from_node}
                )

        # Check for self-referencing edge
        if "from" in edge and "to" in edge and edge["from"] == edge["to"]:
            errors.append(
                {"type": "edge_self_reference", "edge_id": edge_id, "node_id": edge["from"]}
            )

        return errors

    def _validate_start_output_requirements(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Validate that the graph has at least one start node and one output node.

        - Start node: A node that receives an edge from START sentinel
        - Output node: A node with type "output"
        """
        errors = []

        # Check for at least one START edge (defines entry points)
        start_edges = [e for e in edges if e.get("from") == self.START_NODE_ID]
        if not start_edges:
            errors.append(
                {
                    "type": "no_start_node",
                    "message": "Graph must have at least one start node (connected from START)",
                }
            )

        # Check for at least one output node
        output_nodes = [n for n in nodes if n.get("type") == "output"]
        if not output_nodes:
            errors.append(
                {
                    "type": "no_output_node",
                    "message": "Graph must have at least one output node",
                }
            )

        return errors

    def _check_for_cycles(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """
        Check if the graph contains cycles using DFS.

        Returns an error dict if a cycle is found, None otherwise.
        """
        # Build adjacency list
        adjacency: dict[str, list[str]] = defaultdict(list)
        node_ids = {node["id"] for node in nodes}

        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")
            if from_node and to_node:
                adjacency[from_node].append(to_node)

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = dict.fromkeys(node_ids, WHITE)
        cycle_nodes = []

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adjacency[node]:
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle
                    cycle_nodes.append(neighbor)
                    return True
                if color[neighbor] == WHITE:
                    if dfs(neighbor):
                        cycle_nodes.append(node)
                        return True
            color[node] = BLACK
            return False

        for node_id in node_ids:
            if color[node_id] == WHITE:
                if dfs(node_id):
                    return {"type": "cycle_detected", "nodes": list(reversed(cycle_nodes))}

        return None

    def _find_disconnected_nodes(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Find nodes that have no incoming or outgoing edges.

        Returns warnings for disconnected nodes.
        """
        warnings = []
        node_ids = {node["id"] for node in nodes}

        # Build sets of connected nodes
        nodes_with_incoming = set()
        nodes_with_outgoing = set()

        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")

            if from_node and from_node != self.START_NODE_ID:
                nodes_with_outgoing.add(from_node)
            if to_node and to_node != self.END_NODE_ID:
                nodes_with_incoming.add(to_node)

            # START edges give the target node an incoming edge
            if from_node == self.START_NODE_ID and to_node:
                nodes_with_incoming.add(to_node)
            # END edges give the source node an outgoing edge
            if to_node == self.END_NODE_ID and from_node:
                nodes_with_outgoing.add(from_node)

        # Find completely disconnected nodes (no edges at all)
        for node_id in node_ids:
            has_incoming = node_id in nodes_with_incoming
            has_outgoing = node_id in nodes_with_outgoing

            if not has_incoming and not has_outgoing:
                warnings.append(
                    {
                        "type": "disconnected_node",
                        "severity": "warning",
                        "node_id": node_id,
                        "message": f"Node '{node_id}' has no connections",
                        "suggestion": "Connect this node to the workflow or remove it",
                    }
                )

        return warnings

    def _validate_node_configs(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate node configs against their type schemas.

        Only called in strict mode.
        """
        errors = []

        try:
            from domain.value_objects.node_schemas import validate_node_config
        except ImportError:
            # Schemas not defined yet, skip validation
            return errors

        for node in nodes:
            node_id = node.get("id", "unknown")
            node_type = node.get("type")
            config = node.get("config", {})

            if not node_type:
                continue

            config_errors = validate_node_config(node_type, config)
            for error in config_errors:
                errors.append(
                    {
                        "type": "invalid_node_config",
                        "node_id": node_id,
                        "node_type": node_type,
                        "field": error.get("field"),
                        "message": error.get("message"),
                        "suggestion": error.get("suggestion"),
                    }
                )

        return errors
