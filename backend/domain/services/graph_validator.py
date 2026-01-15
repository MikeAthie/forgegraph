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

    def validate(self, graph_json: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Validate a graph JSON structure.

        Returns a list of validation errors. Empty list means valid.
        Raises GraphValidationError for critical structural issues.
        """
        errors = []

        # Check required top-level keys
        if "nodes" not in graph_json:
            errors.append({"type": "missing_key", "key": "nodes"})
        if "edges" not in graph_json:
            errors.append({"type": "missing_key", "key": "edges"})

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

        # Check for cycles (DAG validation)
        if not errors:
            cycle_error = self._check_for_cycles(nodes, edges)
            if cycle_error:
                errors.append(cycle_error)

        return errors

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
        elif edge["from"] not in node_ids:
            errors.append(
                {"type": "edge_invalid_from", "edge_id": edge_id, "from_node": edge["from"]}
            )

        if "to" not in edge:
            errors.append({"type": "edge_missing_to", "edge_id": edge_id})
        elif edge["to"] not in node_ids:
            errors.append({"type": "edge_invalid_to", "edge_id": edge_id, "to_node": edge["to"]})

        # Check for self-referencing edge
        if "from" in edge and "to" in edge and edge["from"] == edge["to"]:
            errors.append(
                {"type": "edge_self_reference", "edge_id": edge_id, "node_id": edge["from"]}
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
