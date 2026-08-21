"""Phase 29 · Security boundary tests for Developer Context.

The developer context layer must be strictly read-only: no path traversal, no
workspace escape, no .env/secret exposure, bounded budgets, project isolation,
no shell execution, no source modification, no auto approval, and no way to
bypass the existing permission boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.context.dev.security import is_sensitive_path, redact_secrets
from app.security.permissions import ACTION_LEVELS


def write_secret_project(bridge) -> None:
    (bridge.demo / ".env").write_text("OPENAI_API_KEY=sk-secret-value-123\nDATABASE_URL=postgres://user:pass@db\n", encoding="utf-8")
    (bridge.demo / "src" / "config.ts").write_text("const apiKey = 'sk-live-abcdef';\nconst password = 'hunter2';\n", encoding="utf-8")
    (bridge.demo / "credentials.json").write_text('{"client_secret": "topsecret"}\n', encoding="utf-8")
    (bridge.demo / "id_rsa.pem").write_text("-----BEGIN PRIVATE KEY-----\nAAAA\n", encoding="utf-8")
    (bridge.demo / "src" / "deep").mkdir(parents=True)
    (bridge.demo / "src" / "deep" / "nested.py").write_text("VALUE = 42\n", encoding="utf-8")


class TestSensitivePathFilter:
    def test_env_is_sensitive(self) -> None:
        assert is_sensitive_path(".env")
        assert is_sensitive_path("config/.env.local")
        assert is_sensitive_path("sub/.env.production")

    def test_key_material_is_sensitive(self) -> None:
        assert is_sensitive_path("keys/id_rsa")
        assert is_sensitive_path("cert/server.pem")
        assert is_sensitive_path("certs/client.key")
        assert is_sensitive_path("credentials.json")

    def test_git_internals_are_sensitive(self) -> None:
        assert is_sensitive_path(".git/config")
        assert is_sensitive_path("sub/.git/HEAD")

    def test_regular_files_are_not_sensitive(self) -> None:
        assert not is_sensitive_path("src/main.py")
        assert not is_sensitive_path("README.md")
        assert not is_sensitive_path("package.json")


class TestSecretRedaction:
    def test_assignment_redaction(self) -> None:
        out = redact_secrets("OPENAI_API_KEY=sk-abc123")
        assert "sk-abc123" not in out
        assert "***REDACTED***" in out

    def test_key_value_redaction(self) -> None:
        out = redact_secrets('"apiKey": "sk-live-abcdef"')
        assert "sk-live-abcdef" not in out

    def test_token_redaction(self) -> None:
        out = redact_secrets("Authorization: Bearer eyJhbGciOi")
        assert "eyJhbGciOi" not in out
        assert "***REDACTED***" in out

    def test_password_redaction(self) -> None:
        out = redact_secrets("password=hunter2")
        assert "hunter2" not in out


class TestPathTraversal:
    def test_traversal_rejected(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/../../etc/passwd", params={"project": "demo"})
        assert response.status_code in (403, 404, 422)

    def test_absolute_path_rejected(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/etc/passwd", params={"project": "demo"})
        assert response.status_code in (403, 404, 422)

    def test_encoded_traversal_rejected(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/..%2F..%2Fetc%2Fpasswd", params={"project": "demo"})
        assert response.status_code in (403, 404, 422)

    def test_workspace_escape_rejected(self, bridge) -> None:
        write_secret_project(bridge)
        outside = bridge.projects_root.parent / "secret-outside.txt"
        outside.write_text("nope", encoding="utf-8")
        response = bridge.client.get("/context/dev/file/../secret-outside.txt", params={"project": "demo"})
        assert response.status_code in (403, 404, 422)

    def test_unknown_project_rejected(self, bridge) -> None:
        assert bridge.client.get("/context/dev/project", params={"project": "ghost"}).status_code in (404, 422)

    def test_invalid_project_name_rejected(self, bridge) -> None:
        for bad in ["../demo", "a/b", ".hidden", ".."]:
            response = bridge.client.get("/context/dev/project", params={"project": bad})
            assert response.status_code in (403, 422), bad


class TestSecretExposure:
    def test_env_content_never_returned(self, bridge) -> None:
        write_secret_project(bridge)
        body = bridge.client.get("/context/dev/bundle", params={"project": "demo"}).json()
        dumped = str(body)
        assert "sk-secret-value-123" not in dumped
        assert "postgres://user:pass@db" not in dumped

    def test_credentials_json_blocked(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/credentials.json", params={"project": "demo"})
        assert response.status_code in (403, 404)

    def test_env_file_blocked(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/.env", params={"project": "demo"})
        assert response.status_code in (403, 404)

    def test_pem_file_blocked(self, bridge) -> None:
        write_secret_project(bridge)
        response = bridge.client.get("/context/dev/file/id_rsa.pem", params={"project": "demo"})
        assert response.status_code in (403, 404)

    def test_secret_looking_values_redacted_in_allowed_files(self, bridge) -> None:
        write_secret_project(bridge)
        body = bridge.client.get("/context/dev/file/src/config.ts", params={"project": "demo"}).json()
        dumped = str(body)
        assert "sk-live-abcdef" not in dumped
        assert "hunter2" not in dumped


class TestBudget:
    def test_oversized_file_truncated(self, bridge) -> None:
        (bridge.demo / "src" / "big.txt").write_text("y" * 200000, encoding="utf-8")
        response = bridge.client.get("/context/dev/file/src/big.txt", params={"project": "demo", "max_file_kb": 8})
        data = response.json()["data"]
        assert data["truncated"] is True
        assert len(data["content"].encode("utf-8")) < 16 * 1024

    def test_symbol_limit_enforced(self, bridge) -> None:
        for index in range(20):
            (bridge.demo / "src" / f"mod{index}.py").write_text(f"def fn{index}():\n    pass\n", encoding="utf-8")
        body = bridge.client.get("/context/dev/symbols", params={"project": "demo", "limit": 3}).json()
        assert len(body["data"]["symbols"]) <= 3

    def test_bundle_size_reported(self, bridge) -> None:
        write_secret_project(bridge)
        body = bridge.client.get("/context/dev/bundle", params={"project": "demo"}).json()
        assert body["size"] > 0
        assert "truncated" in body


class TestIsolation:
    def test_project_isolation(self, bridge) -> None:
        write_secret_project(bridge)
        other = bridge.projects_root / "other"
        other.mkdir()
        (other / "secret.txt").write_text("other-project-data", encoding="utf-8")
        response = bridge.client.get("/context/dev/file/secret.txt", params={"project": "demo"})
        assert response.status_code == 404
        dumped = str(response.content)
        assert "other-project-data" not in dumped

    def test_no_context_dev_actions_in_approval_levels(self) -> None:
        for action in ACTION_LEVELS:
            assert not action.startswith("context_dev"), action


class TestNoExecution:
    def test_no_post_endpoints(self, bridge) -> None:
        for endpoint in (
            "/context/dev/bundle",
            "/context/dev/project",
            "/context/dev/git",
            "/context/dev/tests",
        ):
            assert bridge.client.post(endpoint, json={"project": "demo"}).status_code in (404, 405)

    def test_no_auto_approval(self, bridge) -> None:
        write_secret_project(bridge)
        before = bridge.client.get("/permission/pending").json()
        bridge.client.get("/context/dev/bundle", params={"project": "demo"})
        bridge.client.get("/context/dev/git", params={"project": "demo"})
        after = bridge.client.get("/permission/pending").json()
        assert len(before) == len(after)

    def test_no_shell_executor_in_context_package(self) -> None:
        import app.context.dev as dev

        root = Path(dev.__file__).parent
        for source in root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "shell=True" not in text, source
            assert "os.system" not in text, source
            assert "subprocess.Popen" not in text, source

    def test_context_reads_leave_files_unchanged(self, bridge) -> None:
        write_secret_project(bridge)
        before = {path.relative_to(bridge.demo).as_posix(): path.read_bytes() for path in bridge.demo.rglob("*") if path.is_file()}
        bridge.client.get("/context/dev/bundle", params={"project": "demo"})
        bridge.client.get("/context/dev/dependencies", params={"project": "demo"})
        bridge.client.get("/context/dev/symbols", params={"project": "demo"})
        after = {path.relative_to(bridge.demo).as_posix(): path.read_bytes() for path in bridge.demo.rglob("*") if path.is_file()}
        assert after == before


class TestAgentIsolation:
    def test_agent_param_is_metadata_only(self, bridge) -> None:
        write_secret_project(bridge)
        body = bridge.client.get("/context/dev/bundle", params={"project": "demo", "agent": "PLANNER"}).json()
        assert body["agent"] == "PLANNER"
        # No agent-scoped data is exposed: bundle is project-scoped only.
        assert "agents" not in body
