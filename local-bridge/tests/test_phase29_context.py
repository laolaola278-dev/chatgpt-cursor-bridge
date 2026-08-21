"""Phase 29 · Advanced Developer Context & Read-only Code Intelligence tests.

Covers the context bundle API, project / file / symbol / dependency / git /
test contexts, budgets and truncation, and the read-only boundary.
"""

from __future__ import annotations

import subprocess

from app.code_intelligence.parser import parse_source

from tests.conftest import Bridge


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def init_repo(bridge: Bridge) -> None:
    git(bridge.demo, "init", "-b", "main")
    git(bridge.demo, "config", "user.email", "test@example.com")
    git(bridge.demo, "config", "user.name", "CCB Test")
    git(bridge.demo, "add", "--all")
    git(bridge.demo, "commit", "-m", "initial")


def write_demo_project(bridge: Bridge) -> None:
    (bridge.demo / "src" / "types.ts").write_text(
        "export interface User { id: number }\nexport type Role = 'admin' | 'dev';\nenum Level { A }\nexport const maxRetries = 3;\n",
        encoding="utf-8",
    )
    (bridge.demo / "package.json").write_text(
        '{"name": "demo", "dependencies": {"react": "^18.0.0"}, "devDependencies": {"typescript": "^5.0.0"}}\n',
        encoding="utf-8",
    )
    (bridge.demo / "requirements.txt").write_text("fastapi>=0.100\npytest==7.4\n", encoding="utf-8")
    (bridge.demo / "src" / "big.py").write_text("x = 1\n" * 30000, encoding="utf-8")


class TestBundleEnvelope:
    def test_bundle_has_standard_envelope(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/bundle", params={"project": "demo"}).json()
        assert body["source"] == "context/dev"
        assert body["project"] == "demo"
        assert body["agent"] == "ASSISTANT"
        assert body["contextType"] == "bundle"
        assert body["generatedAt"]
        assert body["size"] > 0
        assert body["truncated"] is False
        assert body["securityFiltering"] is True

    def test_bundle_contains_all_context_sections(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/bundle", params={"project": "demo"}).json()
        assert body["projectContext"]["project"] == "demo"
        assert body["files"]
        assert body["symbols"]["total"] >= 0
        assert "dependencies" in body
        assert body["git"]["branch"]
        assert "tests" in body


class TestProjectContext:
    def test_project_context_languages_and_files(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/project", params={"project": "demo"}).json()
        data = body["data"]
        assert data["project"] == "demo"
        assert "Python" in data["languages"]
        assert "TypeScript" in data["languages"]
        assert data["fileCount"] >= 3
        assert "workspaceRoot" in data

    def test_project_context_package_managers(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/project", params={"project": "demo"}).json()
        managers = body["data"]["packageManagers"]
        assert "npm" in managers
        assert "pip" in managers


class TestFileContext:
    def test_file_context_reads_content_and_symbols(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/file/src/types.ts", params={"project": "demo"}).json()
        data = body["data"]
        assert data["path"] == "src/types.ts"
        assert "interface User" in data["content"]
        assert data["language"] == "TypeScript"
        assert data["exported"] is True
        assert any(s["type"] == "interface" for s in data["symbols"])
        assert any(s["type"] == "variable" for s in data["symbols"])

    def test_file_context_oversized_file_is_truncated(self, bridge) -> None:
        write_demo_project(bridge)
        response = bridge.client.get(
            "/context/dev/file/src/big.py",
            params={"project": "demo", "max_file_kb": 1},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["truncated"] is True
        assert "[file truncated]" in data["content"]

    def test_file_context_unknown_file_404(self, bridge) -> None:
        assert bridge.client.get("/context/dev/file/missing.py", params={"project": "demo"}).status_code == 404


class TestSymbolContext:
    def test_symbol_types_parsed(self, tmp_path) -> None:
        source = tmp_path / "types.ts"
        source.write_text(
            "export interface User { id: number }\nexport type Role = string;\nenum Level { A }\nexport const retries = 3;\nexport function run() {}\nclass Service {}\n",
            encoding="utf-8",
        )
        symbols, _ = parse_source(source, "types.ts")
        kinds = {symbol.symbol_type for symbol in symbols}
        assert {"interface", "type", "enum", "variable", "function", "class"} <= kinds

    def test_symbols_endpoint(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/symbols", params={"project": "demo"}).json()
        symbols = body["data"]["symbols"]
        types = {s["type"] for s in symbols}
        assert "function" in types or "interface" in types
        for symbol in symbols:
            assert symbol["id"]
            assert symbol["file"]
            assert symbol["line"] >= 1

    def test_symbol_search(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/symbols", params={"project": "demo", "q": "User"}).json()
        assert any(s["name"] == "User" for s in body["data"]["symbols"])

    def test_symbol_detail_by_id(self, bridge) -> None:
        write_demo_project(bridge)
        listed = bridge.client.get("/context/dev/symbols", params={"project": "demo", "q": "User"}).json()["data"]["symbols"]
        assert listed
        detail = bridge.client.get(f"/context/dev/symbol/{listed[0]['id']}", params={"project": "demo"}).json()
        assert detail["data"]["id"] == listed[0]["id"]

    def test_symbol_detail_missing_404(self, bridge) -> None:
        assert bridge.client.get("/context/dev/symbol/doesnotexist", params={"project": "demo"}).status_code == 404


class TestDependencyContext:
    def test_dependencies_from_manifests(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/dependencies", params={"project": "demo"}).json()
        names = {dep["name"] for dep in body["data"]["dependencies"]}
        assert "react" in names
        assert "fastapi" in names
        assert "pytest" in names
        sources = {dep["sourceFile"] for dep in body["data"]["dependencies"]}
        assert "package.json" in sources
        assert "requirements.txt" in sources

    def test_dependency_types(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/dependencies", params={"project": "demo"}).json()
        by_name = {dep["name"]: dep for dep in body["data"]["dependencies"]}
        assert by_name["react"]["type"] == "runtime"
        assert by_name["typescript"]["type"] == "dev"


class TestGitContext:
    def test_git_context_reports_branch_and_changes(self, bridge) -> None:
        write_demo_project(bridge)
        init_repo(bridge)
        (bridge.demo / "src" / "main.py").write_text("print('edited')\n", encoding="utf-8")
        body = bridge.client.get("/context/dev/git", params={"project": "demo"}).json()["data"]
        assert body["branch"] == "main"
        assert body["clean"] is False
        assert "src/main.py" in body["changedFiles"]
        assert body["commits"][0]["hash"]

    def test_git_context_commits_limited(self, bridge) -> None:
        write_demo_project(bridge)
        init_repo(bridge)
        body = bridge.client.get("/context/dev/git", params={"project": "demo"}).json()["data"]
        assert len(body["commits"]) >= 1

    def test_git_context_redacts_secrets_in_diff(self, bridge) -> None:
        write_demo_project(bridge)
        init_repo(bridge)
        (bridge.demo / "config.local.js").write_text("const token = 'super-secret-value-123';\n", encoding="utf-8")
        body = bridge.client.get("/context/dev/git", params={"project": "demo"}).json()["data"]
        assert "super-secret-value-123" not in body["diff"]

    def test_git_context_never_mutates_worktree(self, bridge) -> None:
        write_demo_project(bridge)
        init_repo(bridge)
        before = git(bridge.demo, "status", "--porcelain").stdout
        bridge.client.get("/context/dev/git", params={"project": "demo"})
        after = git(bridge.demo, "status", "--porcelain").stdout
        assert before == after


class TestTestContext:
    def test_test_context_unknown_when_no_workflow(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/tests", params={"project": "demo"}).json()["data"]
        assert body["testStatus"] is None

    def test_test_context_after_recorded_result(self, bridge) -> None:
        from app.audit.logger import get_audit_logger
        from app.config import get_settings
        from app.security.permissions import get_approval_store
        from app.workflow.manager import WorkflowManager
        from app.workflow.storage import WorkflowStorage

        workflow = bridge.client.post("/workflow/create", json={"project": "demo", "name": "ctx"}).json()
        stage = None
        for stage_type in ("REQUIREMENT", "ANALYSIS", "ARCHITECTURE", "IMPLEMENTATION", "TESTING"):
            stage = bridge.client.post(f"/workflow/{workflow['id']}/stage/start", json={"stage_type": stage_type}).json()
            assert "id" in stage, stage
        settings = get_settings()
        workflows = WorkflowManager(
            settings=settings,
            storage=WorkflowStorage(settings.workflow_root),
            approvals=get_approval_store(),
            audit=get_audit_logger(),
        )
        workflows.record_test_result(
            workflow["id"],
            stage["id"],
            command="pytest -q",
            passed=True,
            timed_out=False,
            exit_code=0,
            stdout="3 passed",
            stderr="",
        )
        body = bridge.client.get("/context/dev/tests", params={"project": "demo"}).json()["data"]
        assert body["testStatus"]["status"] == "passed"


class TestFilesEndpoint:
    def test_files_list_bounded(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/files", params={"project": "demo", "limit": 2}).json()
        assert len(body["files"]) <= 2
        assert body["truncated"] is True or len(body["files"]) <= 2

    def test_files_list_excludes_sensitive(self, bridge) -> None:
        write_demo_project(bridge)
        (bridge.demo / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (bridge.demo / "id_rsa.pem").write_text("PRIVATE\n", encoding="utf-8")
        body = bridge.client.get("/context/dev/files", params={"project": "demo"}).json()
        assert not any(f["path"] == ".env" for f in body["files"])
        assert not any("id_rsa.pem" in f["path"] for f in body["files"])


class TestReadOnlyBoundary:
    def test_all_endpoints_are_read_only(self, bridge) -> None:
        assert bridge.client.post("/context/dev/bundle", json={"project": "demo"}).status_code in (404, 405)
        assert bridge.client.put("/context/dev/bundle", json={"project": "demo"}).status_code in (404, 405)
        assert bridge.client.patch("/context/dev/bundle", json={"project": "demo"}).status_code in (404, 405)
        assert bridge.client.delete("/context/dev/bundle").status_code in (404, 405)

    def test_context_reads_do_not_modify_files(self, bridge) -> None:
        write_demo_project(bridge)
        before = (bridge.demo / "src" / "main.py").read_bytes()
        bridge.client.get("/context/dev/bundle", params={"project": "demo"})
        bridge.client.get("/context/dev/file/src/main.py", params={"project": "demo"})
        assert (bridge.demo / "src" / "main.py").read_bytes() == before

    def test_status_endpoint(self, bridge) -> None:
        write_demo_project(bridge)
        body = bridge.client.get("/context/dev/status", params={"project": "demo"}).json()
        assert body["project"] == "demo"
        assert body["available"]["project"] is True
        assert body["available"]["git"] is True
        assert body["securityFiltering"] is True
