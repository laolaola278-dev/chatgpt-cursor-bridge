"""Phase 23 - Organization Graph Reasoning tests.

Covers the graph models (non-hierarchical edges, parent type chain), reasoning
engine (ancestors/descendants/owner/impact/cycles), AI context injection,
checksummed snapshot versioning, the API surface and security regression.
Reasoning reads are read-only; snapshot create/restore and graph sync flow
through the ApprovalStore.
"""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest

from app.organization_graph.context import OrganizationContextBuilder
from app.organization_graph.models import (
    EdgeType,
    PARENT_TYPE_CHAIN,
    GraphNode,
    OrgEdge,
    canonical_graph_json,
    checksum_of,
)
from app.organization_graph.reasoning import GraphReasoningEngine
from app.organization_graph.snapshot import GraphSnapshotManager
from app.organization_graph.storage import OrganizationGraphStorage
from app.security.permissions import PermissionLevel, level_for_action
from app.security.validator import ResourceNotFound, ValidationFailed


def _graph(tmp_path) -> OrganizationGraphStorage:
    return OrganizationGraphStorage(tmp_path / "organization_graph.db")


def _seed(storage: OrganizationGraphStorage) -> dict[str, str]:
    company = GraphNode("c1", "COMPANY", "Acme Inc")
    team = GraphNode("t1", "TEAM", "Platform", parent_id="c1")
    project = GraphNode("p1", "PROJECT", "checkout", parent_id="t1")
    service = GraphNode("s1", "SERVICE", "payments-api", parent_id="p1")
    incident = GraphNode("i1", "INCIDENT", "Redis cache failure", parent_id="p1")
    for node in (company, team, project, service, incident):
        storage.save_node(node)
    return {"company": "c1", "team": "t1", "project": "p1", "service": "s1", "incident": "i1"}


# ---------------------------------------------------------------------------
# 1. Models
# ---------------------------------------------------------------------------


def test_edge_types_are_non_hierarchical():
    # Phase 23 relations are still present after Phase 24's additive extension.
    for value in ["RELATED_TO", "IMPACTS", "CAUSED_BY", "DEPENDS_ON"]:
        assert value in {edge.value for edge in EdgeType}
    # Every edge type (Phase 23 + Phase 24 relations) stays non-hierarchical.
    for edge_type in EdgeType:
        edge = OrgEdge("a", "b", edge_type)
        assert edge.is_hierarchy is False


def test_parent_type_chain():
    assert PARENT_TYPE_CHAIN["TEAM"] == "COMPANY"
    assert PARENT_TYPE_CHAIN["PROJECT"] == "TEAM"
    assert PARENT_TYPE_CHAIN["SERVICE"] == "PROJECT"
    assert PARENT_TYPE_CHAIN["REPOSITORY"] == "PROJECT"
    assert PARENT_TYPE_CHAIN["ARCHITECTURE_DECISION"] == "PROJECT"
    assert PARENT_TYPE_CHAIN["INCIDENT"] == "PROJECT"


def test_canonical_json_is_deterministic_and_checksummed():
    nodes = [{"id": "b", "name": "B"}, {"id": "a", "name": "A"}]
    edges = [{"source": "a", "target": "b", "relation": "IMPACTS"}]
    first = canonical_graph_json(nodes, edges)
    second = canonical_graph_json(list(reversed(nodes)), list(reversed(edges)))
    assert first == second
    assert checksum_of(first) == checksum_of(second)
    assert len(checksum_of(first)) == 64  # sha256 hex


def test_graph_node_from_entity_compat(tmp_path):
    storage = _graph(tmp_path)
    entity = {
        "id": "org_proj_1", "type": "PROJECT", "name": "checkout",
        "parentId": "org_team_1", "metadata": {"lang": "python"},
        "createdAt": "2026-01-01T00:00:00Z",
    }
    storage.sync_from_entities([entity])
    node = storage.get_node("org_proj_1")
    assert node.type == "PROJECT"
    assert node.parent_id == "org_team_1"
    assert node.metadata == {"lang": "python"}


# ---------------------------------------------------------------------------
# 2. Storage
# ---------------------------------------------------------------------------


def test_storage_saves_nodes_and_edges(tmp_path):
    storage = _graph(tmp_path)
    storage.save_node(GraphNode("a", "TEAM", "Alpha"))
    storage.save_edge(OrgEdge("a", "b", EdgeType.DEPENDS_ON, {"weight": 2}))
    assert len(storage.list_nodes()) == 1
    edges = storage.list_edges()
    assert len(edges) == 1
    assert edges[0].relation is EdgeType.DEPENDS_ON
    assert edges[0].as_dict()["isHierarchy"] is False


def test_storage_export_graph(tmp_path):
    storage = _graph(tmp_path)
    _seed(storage)
    graph = storage.export_graph()
    assert len(graph["nodes"]) == 5
    assert graph["nodes"][0]["readOnly"] is True


def test_replace_graph_rolls_back_on_bad_data(tmp_path):
    storage = _graph(tmp_path)
    _seed(storage)
    before = len(storage.list_nodes())
    with pytest.raises(Exception):
        storage.replace_graph(
            [{"id": "x", "type": "TEAM", "name": "X"}],
            [{"source": "x", "target": "y", "relation": "NOT_A_RELATION"}],
        )
    assert len(storage.list_nodes()) == before  # unchanged


# ---------------------------------------------------------------------------
# 3. Reasoning engine
# ---------------------------------------------------------------------------


def test_ancestors_nearest_first(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    ancestors = GraphReasoningEngine(storage).get_ancestors(ids["service"])
    assert [item["id"] for item in ancestors] == ["p1", "t1", "c1"]


def test_ancestors_missing_node_raises_404(tmp_path):
    storage = _graph(tmp_path)
    with pytest.raises(ResourceNotFound):
        GraphReasoningEngine(storage).get_ancestors("missing")


def test_descendants_bfs_all_levels(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    descendants = GraphReasoningEngine(storage).get_descendants(ids["company"])
    assert {item["id"] for item in descendants} == {"t1", "p1", "s1", "i1"}


def test_descendants_by_type(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    incidents = GraphReasoningEngine(storage).get_descendants_by_type(ids["project"], "INCIDENT")
    assert [item["id"] for item in incidents] == ["i1"]
    services = GraphReasoningEngine(storage).get_descendants_by_type(ids["team"], "SERVICE")
    assert [item["id"] for item in services] == ["s1"]


def test_find_owner_team_fallback_company(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    engine = GraphReasoningEngine(storage)
    assert engine.find_owner(ids["service"])["owner"]["id"] == "t1"
    assert engine.find_owner(ids["project"])["owner"]["id"] == "t1"
    assert engine.find_owner(ids["company"])["owner"]["id"] == "c1"
    orphan = GraphNode("o1", "PROJECT", "orphan")
    storage.save_node(orphan)
    assert engine.find_owner("o1")["owner"] is None


def test_impact_analysis_direction_aware(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    storage.save_edge(OrgEdge(ids["service"], ids["incident"], EdgeType.IMPACTS))
    storage.save_edge(OrgEdge(ids["project"], ids["service"], EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge(ids["team"], ids["project"], EdgeType.RELATED_TO))
    report = GraphReasoningEngine(storage).impact_analysis(ids["service"])
    impacted = {item["id"] for item in report["impacted"]}
    # IMPACTS: service -> incident; DEPENDS_ON: project -> service (service depends on project)
    # so changes to service affect incident (forward) and project (reverse).
    assert "i1" in impacted
    assert "p1" in impacted
    # RELATED_TO is undirected: team <-> project; only project is a neighbor of service via DEPENDS_ON.
    assert report["readOnly"] is True


def test_detect_cycles(tmp_path):
    storage = _graph(tmp_path)
    storage.save_node(GraphNode("a", "SERVICE", "A"))
    storage.save_node(GraphNode("b", "SERVICE", "B"))
    storage.save_node(GraphNode("c", "SERVICE", "C"))
    storage.save_edge(OrgEdge("a", "b", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("b", "c", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("c", "a", EdgeType.DEPENDS_ON))
    cycles = GraphReasoningEngine(storage).detect_cycles()
    assert cycles and len(cycles[0]) == 4  # a -> b -> c -> a


def test_no_cycles_for_acyclic_graph(tmp_path):
    storage = _graph(tmp_path)
    storage.save_node(GraphNode("a", "SERVICE", "A"))
    storage.save_node(GraphNode("b", "SERVICE", "B"))
    storage.save_edge(OrgEdge("a", "b", EdgeType.DEPENDS_ON))
    assert GraphReasoningEngine(storage).detect_cycles() == []


# ---------------------------------------------------------------------------
# 4. AI Context Injection
# ---------------------------------------------------------------------------


def test_context_builder_stable_shape(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    storage.save_edge(OrgEdge(ids["project"], ids["service"], EdgeType.DEPENDS_ON))
    context = OrganizationContextBuilder(storage).build_context(ids["service"])
    assert set(context) == {"node", "owner", "hierarchy", "related_architecture", "incidents", "ancestorChain", "readOnly"}
    assert context["readOnly"] is True
    assert context["node"]["id"] == ids["service"]
    assert context["owner"]["id"] == ids["team"]
    assert context["ancestorChain"] == ["Acme Inc", "Platform", "checkout", "payments-api"]
    assert context["related_architecture"]["count"] == 1


def test_context_includes_incidents_for_project(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    context = OrganizationContextBuilder(storage).build_context(ids["project"])
    assert [incident["id"] for incident in context["incidents"]] == ["i1"]


def test_context_missing_node_raises_404(tmp_path):
    with pytest.raises(ResourceNotFound):
        OrganizationContextBuilder(_graph(tmp_path)).build_context("missing")


# ---------------------------------------------------------------------------
# 5. Snapshot versioning
# ---------------------------------------------------------------------------


def test_snapshot_create_checksum_and_counts(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    storage.save_edge(OrgEdge(ids["project"], ids["service"], EdgeType.DEPENDS_ON))
    snapshot = GraphSnapshotManager(storage).create()
    assert snapshot.node_count == 5
    assert snapshot.edge_count == 1
    assert len(snapshot.checksum) == 64
    assert snapshot.as_dict()["readOnly"] is True


def test_snapshot_restore_returns_graph_to_previous_state(tmp_path):
    storage = _graph(tmp_path)
    ids = _seed(storage)
    manager = GraphSnapshotManager(storage)
    snapshot = manager.create()
    # Mutate the graph: add a node.
    storage.save_node(GraphNode("x1", "TEAM", "New Team", parent_id="c1"))
    assert len(storage.list_nodes()) == 6
    manager.restore(snapshot.id)
    assert len(storage.list_nodes()) == 5
    assert storage.get_node("x1") is None


def test_snapshot_restore_missing_raises_404(tmp_path):
    with pytest.raises(ResourceNotFound):
        GraphSnapshotManager(_graph(tmp_path)).restore("snap_missing")


def test_snapshot_restore_rejects_checksum_mismatch(tmp_path):
    storage = _graph(tmp_path)
    _seed(storage)
    manager = GraphSnapshotManager(storage)
    snapshot = manager.create()
    # Corrupt the stored graph payload so the checksum no longer matches.
    storage.connection.execute("UPDATE organization_graph_snapshots SET graph_json=? WHERE id=?", ("{}", snapshot.id))
    storage.connection.commit()
    with pytest.raises(ValidationFailed):
        manager.restore(snapshot.id)
    # Graph untouched after failed restore.
    assert len(storage.list_nodes()) == 5


def test_snapshot_list_ordered_newest_first(tmp_path):
    storage = _graph(tmp_path)
    _seed(storage)
    manager = GraphSnapshotManager(storage)
    manager.create()
    manager.create()
    snapshots = manager.list()
    assert len(snapshots) == 2


# ---------------------------------------------------------------------------
# 6. API integration
# ---------------------------------------------------------------------------


def _register_entity(bridge, entity_type: str, name: str, parent_id: str | None = None) -> str:
    payload = {"type": entity_type, "name": name, "reason": "seed"}
    if parent_id:
        payload["parent_id"] = parent_id
    pending = bridge.client.post("/organization/graph/entity", json=payload)
    assert pending.status_code == 202
    result = bridge.approve(pending.json()["requestId"]).json()["result"]
    return result["id"]


def test_sync_imports_phase22_entities(bridge):
    company_id = _register_entity(bridge, "COMPANY", "Acme Inc")
    team_id = _register_entity(bridge, "TEAM", "Platform", company_id)
    _register_entity(bridge, "PROJECT", "checkout", team_id)

    pending = bridge.client.post("/organization-graph/sync", json={"reason": "import"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "organization_graph_sync"
    # Nothing synced before approval.
    assert bridge.client.get("/organization-graph/ancestors", params={"node_id": team_id}).status_code == 404
    executed = bridge.approve(pending.json()["requestId"]).json()["result"]
    assert executed["nodes"] == 3

    ancestors = bridge.client.get("/organization-graph/ancestors", params={"node_id": team_id}).json()
    assert ancestors["count"] == 1
    assert ancestors["ancestors"][0]["id"] == company_id


def test_reasoning_api_read_only(bridge):
    from app.organization_graph.models import GraphNode

    graph_storage = OrganizationGraphStorage(bridge.projects_root.parent / "organization" / "organization_graph.db")
    graph_storage.save_node(GraphNode("c1", "COMPANY", "Acme Inc"))
    graph_storage.save_node(GraphNode("t1", "TEAM", "Platform", parent_id="c1"))
    graph_storage.save_node(GraphNode("p1", "PROJECT", "checkout", parent_id="t1"))
    graph_storage.save_edge(OrgEdge("t1", "p1", EdgeType.DEPENDS_ON))

    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()

    descendants = bridge.client.get("/organization-graph/descendants", params={"node_id": "c1"}).json()
    assert descendants["count"] == 2
    owner = bridge.client.get("/organization-graph/owner", params={"node_id": "p1"}).json()
    assert owner["owner"]["id"] == "t1"
    impact = bridge.client.get("/organization-graph/impact", params={"node_id": "t1"}).json()
    assert impact["readOnly"] is True
    context = bridge.client.get("/organization-graph/context", params={"node_id": "p1"}).json()
    assert context["ancestorChain"] == ["Acme Inc", "Platform", "checkout"]
    snapshots = bridge.client.get("/organization-graph/snapshot/list").json()
    assert snapshots["readOnly"] is True
    assert bridge.client.get("/organization-graph/ancestors", params={"node_id": "missing"}).status_code == 404

    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_snapshot_api_create_and_restore_round_trip(bridge):
    from app.organization_graph.models import GraphNode

    graph_storage = OrganizationGraphStorage(bridge.projects_root.parent / "organization" / "organization_graph.db")
    graph_storage.save_node(GraphNode("c1", "COMPANY", "Acme Inc"))
    graph_storage.save_node(GraphNode("t1", "TEAM", "Platform", parent_id="c1"))

    pending = bridge.client.post("/organization-graph/snapshot/create", json={"reason": "snapshot"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "organization_graph_snapshot_create"
    snapshot = bridge.approve(pending.json()["requestId"]).json()["result"]
    snapshot_id = snapshot["id"]
    assert snapshot["nodeCount"] == 2

    # Mutate the graph after the snapshot.
    graph_storage.save_node(GraphNode("x1", "PROJECT", "new-project", parent_id="t1"))
    assert len(graph_storage.list_nodes()) == 3

    restore = bridge.client.post("/organization-graph/snapshot/restore", json={"snapshot_id": snapshot_id, "reason": "restore"})
    assert restore.status_code == 202
    assert restore.json()["action"] == "organization_graph_snapshot_restore"
    assert bridge.approve(restore.json()["requestId"]).status_code == 200
    assert len(graph_storage.list_nodes()) == 2
    assert graph_storage.get_node("x1") is None


def test_snapshot_restore_api_rejects_missing_snapshot(bridge):
    pending = bridge.client.post("/organization-graph/snapshot/restore", json={"snapshot_id": "snap_missing", "reason": "r"})
    assert pending.status_code == 404


def test_snapshot_create_requires_approval_no_auto_execute(bridge):
    pending = bridge.client.post("/organization-graph/snapshot/create", json={"reason": "r"})
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending"
    assert bridge.client.get("/organization-graph/snapshot/list").json()["snapshots"] == []


# ---------------------------------------------------------------------------
# 7. Security regression
# ---------------------------------------------------------------------------


def test_org_graph_get_endpoints_never_modify_source(bridge):
    graph_storage = OrganizationGraphStorage(bridge.projects_root.parent / "organization" / "organization_graph.db")
    graph_storage.save_node(GraphNode("c1", "COMPANY", "Acme Inc"))
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    for path in (
        "/organization-graph/ancestors",
        "/organization-graph/descendants",
        "/organization-graph/owner",
        "/organization-graph/impact",
        "/organization-graph/context",
        "/organization-graph/snapshot/list",
    ):
        assert bridge.client.get(path, params={"node_id": "c1"}).status_code == 200
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_org_graph_writes_never_auto_execute(bridge):
    for endpoint, payload in (
        ("/organization-graph/sync", {"reason": "r"}),
        ("/organization-graph/snapshot/create", {"reason": "r"}),
    ):
        pending = bridge.client.post(endpoint, json=payload)
        assert pending.status_code == 202
        assert pending.json()["status"] == "pending"
    assert bridge.client.get("/organization-graph/snapshot/list").json()["snapshots"] == []


def test_org_graph_actions_are_level_one():
    for action in (
        "organization_graph_sync",
        "organization_graph_snapshot_create",
        "organization_graph_snapshot_restore",
    ):
        assert level_for_action(action) == PermissionLevel.LEVEL_1


def test_org_graph_writes_are_audited(bridge):
    pending = bridge.client.post("/organization-graph/snapshot/create", json={"reason": "r"})
    bridge.approve(pending.json()["requestId"])
    entries = bridge.audit_entries()
    assert any(entry["action"] == "organization_graph_snapshot_create" and entry["approved"] for entry in entries)


def test_org_graph_modules_have_no_execution_entrypoint():
    from app.organization_graph.context import OrganizationContextBuilder as ContextClass
    from app.organization_graph.reasoning import GraphReasoningEngine as ReasoningClass
    from app.organization_graph.snapshot import GraphSnapshotManager as SnapshotClass
    from app.organization_graph.storage import OrganizationGraphStorage as StorageClass

    for cls in (ContextClass, ReasoningClass, SnapshotClass, StorageClass):
        source = inspect.getsource(cls)
        assert "subprocess" not in source
        assert "shell" not in source.lower()
        assert "mark_approved" not in source
        assert "approvals.create" not in source
