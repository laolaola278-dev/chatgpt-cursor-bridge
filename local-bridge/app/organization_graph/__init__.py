"""Organization Graph Reasoning (Phase 23).

Read-only reasoning over the organization graph: ancestors, descendants,
owner lookup, impact analysis, cycle detection and AI context injection,
plus approval-gated checksummed snapshot versioning. No module here can
execute actions or modify source code directly.
"""

from .context import OrganizationContextBuilder
from .models import EdgeType, GraphNode, GraphSnapshot, OrgEdge, PARENT_TYPE_CHAIN
from .reasoning import GraphReasoningEngine
from .snapshot import GraphSnapshotManager
from .storage import OrganizationGraphStorage

__all__ = [
    "OrganizationContextBuilder",
    "GraphReasoningEngine",
    "GraphSnapshotManager",
    "OrganizationGraphStorage",
    "EdgeType",
    "GraphNode",
    "GraphSnapshot",
    "OrgEdge",
    "PARENT_TYPE_CHAIN",
]
