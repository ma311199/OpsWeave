"""Permission isolation for retrieval and tool execution.

All retrieval tools and external API calls must pass through
PermissionChecker before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    """Supported user roles for access control."""

    ADMIN = "admin"
    OPS_ENGINEER = "ops_engineer"
    VIEWER = "viewer"


class ResourceType(str, Enum):
    """Resource types that require permission checks."""

    RETRIEVAL_INDEX = "retrieval_index"
    MONITORING_API = "monitoring_api"
    K8S_CLUSTER = "k8s_cluster"
    SECRET_STORE = "secret_store"


@dataclass
class PermissionRule:
    """A single permission rule mapping role + resource to allowed action."""

    role: Role
    resource: ResourceType
    allowed: bool = True


@dataclass
class PermissionChecker:
    """Central permission gate for tool execution.

    Usage::

        checker = PermissionChecker.default_rules()
        if checker.is_allowed(Role.OPS_ENGINEER, ResourceType.RETRIEVAL_INDEX):
            # execute retrieval
            ...
    """

    rules: list[PermissionRule] = field(default_factory=list)

    @staticmethod
    def default_rules() -> PermissionChecker:
        """Return a PermissionChecker with sensible default rules."""
        rules = [
            # admin can do everything
            PermissionRule(Role.ADMIN, ResourceType.RETRIEVAL_INDEX, True),
            PermissionRule(Role.ADMIN, ResourceType.MONITORING_API, True),
            PermissionRule(Role.ADMIN, ResourceType.K8S_CLUSTER, True),
            PermissionRule(Role.ADMIN, ResourceType.SECRET_STORE, True),
            # ops engineer can retrieve and query monitoring, no k8s
            PermissionRule(Role.OPS_ENGINEER, ResourceType.RETRIEVAL_INDEX, True),
            PermissionRule(Role.OPS_ENGINEER, ResourceType.MONITORING_API, True),
            PermissionRule(Role.OPS_ENGINEER, ResourceType.K8S_CLUSTER, False),
            PermissionRule(Role.OPS_ENGINEER, ResourceType.SECRET_STORE, False),
            # viewer can only retrieve, no external calls
            PermissionRule(Role.VIEWER, ResourceType.RETRIEVAL_INDEX, True),
            PermissionRule(Role.VIEWER, ResourceType.MONITORING_API, False),
            PermissionRule(Role.VIEWER, ResourceType.K8S_CLUSTER, False),
            PermissionRule(Role.VIEWER, ResourceType.SECRET_STORE, False),
        ]
        return PermissionChecker(rules=rules)

    def is_allowed(self, role: Role, resource: ResourceType) -> bool:
        """Check if a role is allowed to access a resource."""
        for rule in self.rules:
            if rule.role == role and rule.resource == resource:
                return rule.allowed
        return False  # deny by default

    def require(
        self, role: Role, resource: ResourceType, **context: Any
    ) -> None:
        """Raise PermissionError if access is denied."""
        if not self.is_allowed(role, resource):
            raise PermissionError(
                f"Role {role.value} is not allowed to access {resource.value}"
            )
