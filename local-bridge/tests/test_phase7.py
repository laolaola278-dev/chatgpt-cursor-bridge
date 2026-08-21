"""Phase 7 context, observability and production-hardening tests."""

from __future__ import annotations

from app.audit.logger import AuditLogger
from app.config import get_settings
from app.hardening.maintenance import RecoveryManager
from tests.conftest import Bridge


def test_system_health_reports_all_phase7_domains(bridge: Bridge) -> None:
    response = bridge.client.get("/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["phase"].startswith("phase-7-")
    assert set(body["checks"]) == {"memory", "database", "workspace", "workflow", "approval"}
    assert body["checks"]["memory"]["status"] == "ok"
    assert body["checks"]["workspace"]["status"] == "ok"


def test_project_context_is_read_only_and_writes_snapshot(bridge: Bridge) -> None:
    response = bridge.client.get("/context/project", params={"project": "demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "demo"
    assert body["currentWorkflow"] is None
    assert body["openTasks"] == []
    assert body["pendingApprovals"] == []
    snapshot = get_settings().context_root / "demo" / "current.json"
    assert snapshot.exists()
    assert "recentErrors" in snapshot.read_text(encoding="utf-8")


def test_startup_creates_inspection_backup(bridge: Bridge) -> None:
    backups = sorted(get_settings().backup_root.glob("backup-*"))
    assert backups
    latest = backups[-1]
    assert (latest / "metadata.json").exists()
    assert (latest / "approvals.json").exists()
    assert (latest / "memory").is_dir()
    assert (latest / "workflows").is_dir()


def test_recovery_quarantines_corrupt_workflow_json(bridge: Bridge) -> None:
    corrupt = bridge.workflow_root / "wf_corrupt.json"
    corrupt.write_text("{not-json", encoding="utf-8")
    report = RecoveryManager(get_settings()).run()
    assert report["workflowFilesRecovered"] == 1
    assert not corrupt.exists()
    assert list((get_settings().backup_root / "recovery").glob("wf_corrupt.json.*.corrupt"))


def test_dashboard_is_read_only(bridge: Bridge) -> None:
    response = bridge.client.get("/dashboard")
    assert response.status_code == 200
    assert "read-only dashboard" in response.text
    assert "POST" not in response.text
    assert "/system/health" in response.text


def test_audit_logger_rotates_to_archive(tmp_path) -> None:
    logger = AuditLogger(tmp_path / "audit.jsonl", max_bytes=300)
    for index in range(8):
        logger.record(
            action=f"event_{index}",
            path="demo:test",
            permission="LEVEL_0",
            approved=True,
            result="success",
            detail="x" * 80,
        )
    archives = list((tmp_path / "archive").glob("audit-*.jsonl"))
    assert archives
    assert (tmp_path / "audit.jsonl").exists()
