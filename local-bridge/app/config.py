"""Configuration loading for the local bridge service.

All runtime paths come from environment variables (optionally provided through a
``.env`` file). Nothing is hardcoded outside of the fallback defaults declared
in this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

#: ``local-bridge/`` directory, used to resolve relative configuration paths.
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = "8765"
DEFAULT_WORKSPACE_ROOT = "../workspace/projects"
DEFAULT_LOG_PATH = "../workspace/logs"
DEFAULT_MEMORY_ROOT = "../workspace/memory"
DEFAULT_MAX_MEMORY_APPEND_KB = "64"
DEFAULT_WORKFLOW_ROOT = "../workspace/workflows"
DEFAULT_ROLLBACK_ROOT = "../workspace/rollback"
DEFAULT_CONTEXT_ROOT = "../workspace/context"
DEFAULT_BACKUP_ROOT = "../workspace/backups"
DEFAULT_APPROVAL_DB_PATH = "../workspace/approvals/approvals.db"
DEFAULT_SESSION_ROOT = "../workspace/sessions"
DEFAULT_AGENT_ROOT = "../workspace/agents"
DEFAULT_EVENT_ROOT = "../workspace/events"
DEFAULT_MESSAGE_ROOT = "../workspace/messages"
DEFAULT_RUNTIME_ROOT = "../workspace/runtimes"
DEFAULT_TASK_DB_PATH = "../workspace/tasks/task.db"
DEFAULT_CODE_INDEX_DB_PATH = "../workspace/code/code_index.db"
DEFAULT_KNOWLEDGE_GRAPH_DB_PATH = "../workspace/knowledge/knowledge_graph.db"
DEFAULT_INTELLIGENCE_DB_PATH = "../workspace/intelligence/intelligence.db"
DEFAULT_SIMULATION_DB_PATH = "../workspace/simulation/simulation.db"
DEFAULT_EXECUTION_DB_PATH = "../workspace/execution/execution.db"
DEFAULT_EXECUTION_LOOP_DB_PATH = "../workspace/execution/execution_loop.db"
DEFAULT_EXECUTION_DAG_DB_PATH = "../workspace/execution/execution_dag.db"
DEFAULT_AGENT_PROFILE_DB_PATH = "../workspace/agents/agent_profile.db"
DEFAULT_EXECUTION_SNAPSHOT_ROOT = "../workspace/execution_snapshots"
DEFAULT_AUDIT_MAX_MB = "5"
DEFAULT_BACKUP_INTERVAL_SECONDS = "900"
DEFAULT_APPROVAL_TTL_SECONDS = "3600"
DEFAULT_TEST_TIMEOUT_SECONDS = "300"
DEFAULT_TEST_MAX_OUTPUT_KB = "64"
DEFAULT_MAX_FILE_SIZE_MB = "5"
DEFAULT_MAX_TREE_DEPTH = "6"
DEFAULT_MAX_TREE_ENTRIES = "2000"
DEFAULT_IGNORED_NAMES = "node_modules,.git,.venv,venv,__pycache__,dist,build,.next"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for the bridge."""

    bridge_host: str
    bridge_port: int
    workspace_root: Path
    log_path: Path
    memory_root: Path
    workflow_root: Path
    rollback_root: Path
    context_root: Path
    backup_root: Path
    approval_db_path: Path
    session_root: Path
    agent_root: Path
    event_root: Path
    message_root: Path
    runtime_root: Path
    task_db_path: Path
    code_index_db_path: Path
    knowledge_graph_db_path: Path
    intelligence_db_path: Path
    simulation_db_path: Path
    execution_db_path: Path
    execution_loop_db_path: Path
    execution_dag_db_path: Path
    agent_profile_db_path: Path
    execution_snapshot_root: Path
    audit_max_bytes: int
    backup_interval_seconds: int
    approval_ttl_seconds: int
    test_timeout_seconds: int
    test_max_output_bytes: int
    max_file_size_bytes: int
    max_memory_append_bytes: int
    max_tree_depth: int
    max_tree_entries: int
    ignored_names: tuple[str, ...]

    @property
    def audit_log_file(self) -> Path:
        return self.log_path / "audit.jsonl"

    @property
    def context_index_db_path(self) -> Path:
        return self.context_root / "context_index.db"

    @property
    def governance_db_path(self) -> Path:
        """SQLite database for governance telemetry (health/drift/debt/policy)."""
        return self.workspace_root.parent / "governance" / "governance.db"

    @property
    def organization_db_path(self) -> Path:
        """SQLite database for organization intelligence (graph/patterns/incidents/health)."""
        return self.workspace_root.parent / "organization" / "organization.db"

    @property
    def organization_graph_db_path(self) -> Path:
        """SQLite database for the organization graph reasoning layer (nodes/edges/snapshots)."""
        return self.workspace_root.parent / "organization" / "organization_graph.db"

    @property
    def organization_strategy_db_path(self) -> Path:
        """SQLite database for the organization strategy layer (strategies/decisions/simulations)."""
        return self.workspace_root.parent / "organization" / "organization_strategy.db"

    def ensure_directories(self) -> None:
        """Create all configured service directories."""
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.workflow_root.mkdir(parents=True, exist_ok=True)
        self.rollback_root.mkdir(parents=True, exist_ok=True)
        self.context_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.approval_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.agent_root.mkdir(parents=True, exist_ok=True)
        self.event_root.mkdir(parents=True, exist_ok=True)
        self.message_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.task_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.code_index_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.knowledge_graph_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.intelligence_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.simulation_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.execution_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.execution_loop_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.execution_dag_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.agent_profile_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.execution_snapshot_root.mkdir(parents=True, exist_ok=True)
        (self.memory_root / "evolution").mkdir(parents=True, exist_ok=True)


def _resolve_path(raw_value: str) -> Path:
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    return candidate


def _read_int(name: str, default: str) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be positive, got {value}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process (cache can be cleared in tests)."""
    load_dotenv(BASE_DIR / ".env", override=False)

    ignored_raw = os.getenv("IGNORED_NAMES", DEFAULT_IGNORED_NAMES)
    ignored = tuple(sorted({item.strip() for item in ignored_raw.split(",") if item.strip()}))

    settings = Settings(
        bridge_host=os.getenv("BRIDGE_HOST", DEFAULT_BRIDGE_HOST).strip() or DEFAULT_BRIDGE_HOST,
        bridge_port=_read_int("BRIDGE_PORT", DEFAULT_BRIDGE_PORT),
        workspace_root=_resolve_path(os.getenv("WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT)),
        log_path=_resolve_path(os.getenv("LOG_PATH", DEFAULT_LOG_PATH)),
        memory_root=_resolve_path(os.getenv("MEMORY_ROOT", DEFAULT_MEMORY_ROOT)),
        workflow_root=_resolve_path(os.getenv("WORKFLOW_ROOT", DEFAULT_WORKFLOW_ROOT)),
        rollback_root=_resolve_path(os.getenv("ROLLBACK_ROOT", DEFAULT_ROLLBACK_ROOT)),
        context_root=_resolve_path(os.getenv("CONTEXT_ROOT", DEFAULT_CONTEXT_ROOT)),
        backup_root=_resolve_path(os.getenv("BACKUP_ROOT", DEFAULT_BACKUP_ROOT)),
        approval_db_path=_resolve_path(
            os.getenv("APPROVAL_DB_PATH", DEFAULT_APPROVAL_DB_PATH)
        ),
        session_root=_resolve_path(os.getenv("SESSION_ROOT", DEFAULT_SESSION_ROOT)),
        agent_root=_resolve_path(os.getenv("AGENT_ROOT", DEFAULT_AGENT_ROOT)),
        event_root=_resolve_path(os.getenv("EVENT_ROOT", DEFAULT_EVENT_ROOT)),
        message_root=_resolve_path(os.getenv("MESSAGE_ROOT", DEFAULT_MESSAGE_ROOT)),
        runtime_root=_resolve_path(os.getenv("RUNTIME_ROOT", DEFAULT_RUNTIME_ROOT)),
        task_db_path=_resolve_path(os.getenv("TASK_DB_PATH", DEFAULT_TASK_DB_PATH)),
        code_index_db_path=_resolve_path(
            os.getenv("CODE_INDEX_DB_PATH", DEFAULT_CODE_INDEX_DB_PATH)
        ),
        knowledge_graph_db_path=_resolve_path(
            os.getenv("KNOWLEDGE_GRAPH_DB_PATH", DEFAULT_KNOWLEDGE_GRAPH_DB_PATH)
        ),
        intelligence_db_path=_resolve_path(
            os.getenv("INTELLIGENCE_DB_PATH", DEFAULT_INTELLIGENCE_DB_PATH)
        ),
        simulation_db_path=_resolve_path(
            os.getenv("SIMULATION_DB_PATH", DEFAULT_SIMULATION_DB_PATH)
        ),
        execution_db_path=_resolve_path(
            os.getenv("EXECUTION_DB_PATH", DEFAULT_EXECUTION_DB_PATH)
        ),
        execution_loop_db_path=_resolve_path(
            os.getenv("EXECUTION_LOOP_DB_PATH", DEFAULT_EXECUTION_LOOP_DB_PATH)
        ),
        execution_dag_db_path=_resolve_path(
            os.getenv("EXECUTION_DAG_DB_PATH", DEFAULT_EXECUTION_DAG_DB_PATH)
        ),
        agent_profile_db_path=_resolve_path(
            os.getenv("AGENT_PROFILE_DB_PATH", DEFAULT_AGENT_PROFILE_DB_PATH)
        ),
        execution_snapshot_root=_resolve_path(
            os.getenv("EXECUTION_SNAPSHOT_ROOT", DEFAULT_EXECUTION_SNAPSHOT_ROOT)
        ),
        audit_max_bytes=_read_int("AUDIT_MAX_MB", DEFAULT_AUDIT_MAX_MB) * 1024 * 1024,
        backup_interval_seconds=_read_int(
            "BACKUP_INTERVAL_SECONDS", DEFAULT_BACKUP_INTERVAL_SECONDS
        ),
        approval_ttl_seconds=_read_int(
            "APPROVAL_TTL_SECONDS", DEFAULT_APPROVAL_TTL_SECONDS
        ),
        test_timeout_seconds=_read_int("TEST_TIMEOUT_SECONDS", DEFAULT_TEST_TIMEOUT_SECONDS),
        test_max_output_bytes=_read_int("TEST_MAX_OUTPUT_KB", DEFAULT_TEST_MAX_OUTPUT_KB) * 1024,
        max_file_size_bytes=_read_int("MAX_FILE_SIZE_MB", DEFAULT_MAX_FILE_SIZE_MB) * 1024 * 1024,
        max_memory_append_bytes=_read_int("MAX_MEMORY_APPEND_KB", DEFAULT_MAX_MEMORY_APPEND_KB)
        * 1024,
        max_tree_depth=_read_int("MAX_TREE_DEPTH", DEFAULT_MAX_TREE_DEPTH),
        max_tree_entries=_read_int("MAX_TREE_ENTRIES", DEFAULT_MAX_TREE_ENTRIES),
        ignored_names=ignored,
    )
    settings.ensure_directories()
    return settings


def reset_settings_cache() -> None:
    """Clear the cached settings. Used by tests and by reload flows."""
    get_settings.cache_clear()
