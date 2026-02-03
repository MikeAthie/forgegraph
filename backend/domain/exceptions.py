"""
Domain-specific exceptions.

Clean Architecture: Enterprise Business Rules layer.
These exceptions represent domain-level errors, independent of any framework.
"""

from typing import Any


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, code: str = "domain_error"):
        self.message = message
        self.code = code
        super().__init__(self.message)


# Entity Exceptions
class EntityNotFoundError(DomainException):
    """Raised when an entity cannot be found."""

    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            message=f"{entity_type} with id '{entity_id}' not found", code="entity_not_found"
        )
        self.entity_type = entity_type
        self.entity_id = entity_id


class EntityAlreadyExistsError(DomainException):
    """Raised when trying to create an entity that already exists."""

    def __init__(self, entity_type: str, identifier: str):
        super().__init__(
            message=f"{entity_type} with identifier '{identifier}' already exists",
            code="entity_already_exists",
        )


# Graph Exceptions
class GraphValidationError(DomainException):
    """Raised when a graph fails validation."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message=message, code="graph_validation_error")
        self.errors = errors or []


class CyclicGraphError(GraphValidationError):
    """Raised when a graph contains cycles (not a valid DAG)."""

    def __init__(self, cycle_nodes: list[str] | None = None):
        super().__init__(
            message="Graph contains a cycle and is not a valid DAG",
            errors=[{"type": "cycle", "nodes": cycle_nodes or []}],
        )


class InvalidNodeTypeError(GraphValidationError):
    """Raised when a node has an invalid type."""

    def __init__(self, node_id: str, node_type: str):
        super().__init__(
            message=f"Invalid node type '{node_type}' for node '{node_id}'",
            errors=[{"type": "invalid_node_type", "node_id": node_id, "node_type": node_type}],
        )


class OrphanedNodeError(GraphValidationError):
    """Raised when a node has no connections."""

    def __init__(self, node_id: str):
        super().__init__(
            message=f"Node '{node_id}' has no incoming or outgoing edges",
            errors=[{"type": "orphaned_node", "node_id": node_id}],
        )


class InvalidEdgeError(GraphValidationError):
    """Raised when an edge references non-existent nodes."""

    def __init__(self, edge_id: str, missing_node: str):
        super().__init__(
            message=f"Edge '{edge_id}' references non-existent node '{missing_node}'",
            errors=[{"type": "invalid_edge", "edge_id": edge_id, "missing_node": missing_node}],
        )


# Prompt Exceptions
class PromptValidationError(DomainException):
    """Raised when a prompt fails validation."""

    def __init__(self, message: str):
        super().__init__(message=message, code="prompt_validation_error")


# Run Exceptions
class RunError(DomainException):
    """Base exception for run-related errors."""

    def __init__(self, message: str, code: str = "run_error"):
        super().__init__(message=message, code=code)


class RunAlreadyCompletedError(RunError):
    """Raised when trying to modify a completed run."""

    def __init__(self, run_id: str):
        super().__init__(
            message=f"Run '{run_id}' has already completed", code="run_already_completed"
        )


class RunNotPausedError(RunError):
    """Raised when trying to resume a run that isn't paused."""

    def __init__(self, run_id: str, current_status: str):
        super().__init__(
            message=f"Run '{run_id}' is not paused (current status: {current_status})",
            code="run_not_paused",
        )


# Authorization Exceptions
class AuthorizationError(DomainException):
    """Raised when a user doesn't have permission to perform an action."""

    def __init__(self, message: str = "You don't have permission to perform this action"):
        super().__init__(message=message, code="authorization_error")


class OwnershipError(AuthorizationError):
    """Raised when a user tries to access a resource they don't own."""

    def __init__(self, resource_type: str):
        super().__init__(message=f"You don't have access to this {resource_type}")
