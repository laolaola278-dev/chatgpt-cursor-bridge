"""Phase 33 · Release security boundary tests (spec §22 security group).

Five boundaries, all offline:

* **Secret hygiene of the release artefacts** — nothing under ``release/`` and
  nothing inside the packaged ZIP carries a value-shaped secret, a ``.env``, a
  database or a source map.
* **Secret containment in the Bridge** — a configured key is never returned by
  an endpoint, never written to ``audit.jsonl`` and never stored in plaintext.
* **Tool boundary** — the release re-scan finds no execute / approve-from-chat /
  apply-patch / auto-fix / auto-approve / shell capability, and the packaged
  bundles contain no execution primitive.
* **No auto approval** — a provider write is still 202 pending and only takes
  effect after ``POST /permission/approve``; the Phase 8 approval path is intact.
* **Release tooling is offline** — the auditors and the build script neither
  import a network client nor upload, publish or execute anything.

Nothing here builds, uploads, publishes or approves anything on its own.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from app.assistant.service import NEVER_AVAILABLE
from app.release.audit import forbidden_path_findings, secret_findings
from app.security.permissions import PermissionLevel, level_for_action

REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_DIR = REPO_ROOT / "release"
RELEASE_ARCHIVE = RELEASE_DIR / "AI-Assistant-extension.zip"
BUILD_SCRIPT = RELEASE_DIR / "build-release.sh"
EXTENSION_DIR = REPO_ROOT / "browser-extension"
RELEASE_PACKAGE = Path(__file__).resolve().parents[2] / "app" / "release"

# A key-shaped string that is deliberately not a real credential. It exists so
# the leak tests have something to hunt for; it matches no provider account and
# is never sent anywhere.
SAMPLE_API_KEY = "sk-live-" + "0123456789abcdef0123456789"

# Provider writes stay approval-gated after the release work (§18).
RELEASE_WRITE_ACTIONS = (
    "assistant_provider_config",
    "assistant_provider_forget",
    "assistant_settings_update",
)

# Primitives that must not appear in a packaged runtime bundle.
FORBIDDEN_BUNDLE_TOKENS = (
    "child_process",
    "new Function(",
    "chrome.debugger",
    "declarativeNetRequest",
    "webRequestBlocking",
    "<all_urls>",
    "innerHTML =",
)

# Code shapes — not prose — that would give the release tooling the ability to
# execute or approve something. The auditors *describe* what they refuse to do
# in their docstrings, so a bare word like "approve" is not a finding; a call is.
FORBIDDEN_TOOLING_CODE = (
    "import subprocess",
    "subprocess.",
    "os.system(",
    "os.popen(",
    "eval(",
    "exec(",
    "ApprovalStore",
    ".approve(",
    "shutil.rmtree(",
)

# Commands that would make the release script reach the network.
FORBIDDEN_SCRIPT_COMMANDS = (
    r"\bcurl\b",
    r"\bwget\b",
    r"\bscp\b",
    r"npm\s+publish",
    r"git\s+push",
    r"chrome\.google\.com",
)


def configure_openai(bridge, api_key: str = SAMPLE_API_KEY):
    """Stage + approve a credential so the leak tests have something to leak."""
    pending = bridge.client.post(
        "/provider/config",
        json={"provider": "openai", "model": "gpt-4o", "api_key": api_key, "reason": "configure"},
    )
    assert pending.status_code == 202
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    return pending, executed


def release_text_files() -> list[Path]:
    return sorted(
        path
        for path in RELEASE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".sh", ".json", ".txt"}
    )


def packaged_bundles() -> dict[str, str]:
    """The runtime files as they ship, read out of the ZIP."""
    with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
        return {
            name: bundle.read(name).decode("utf-8", errors="replace")
            for name in bundle.namelist()
        }


def provider_entries(bridge) -> dict[str, dict]:
    """``GET /provider/status`` keyed by provider name."""
    payload = bridge.client.get("/provider/status").json()
    return {entry["provider"]: entry for entry in payload["providers"]}


# -- Release artefacts -------------------------------------------------------

class TestReleaseArtefactSecrets:
    def test_release_directory_exists(self) -> None:
        assert RELEASE_DIR.is_dir()

    def test_no_release_document_carries_a_secret(self) -> None:
        """§13: documentation is audited with the same rules as the package."""
        for path in release_text_files():
            text = path.read_text(encoding="utf-8")
            assert secret_findings(path.name, text) == [], path

    def test_release_directory_holds_no_env_file_or_database(self) -> None:
        for path in RELEASE_DIR.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(RELEASE_DIR).as_posix()
            if relative.endswith(".zip"):
                continue  # audited member-by-member below
            assert forbidden_path_findings(relative) == [], relative

    def test_docs_only_show_placeholder_keys(self) -> None:
        for path in release_text_files():
            text = path.read_text(encoding="utf-8")
            assert re.search(r"sk-[A-Za-z0-9]{16,}", text) is None, path
            assert "Bearer " not in text or "Bearer …" in text, path


class TestPackagedArchiveSecrets:
    @pytest.fixture(autouse=True)
    def require_archive(self) -> None:
        if not RELEASE_ARCHIVE.is_file():
            pytest.skip("release archive not built yet: run release/build-release.sh")

    def test_no_member_is_a_forbidden_file(self) -> None:
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            for name in bundle.namelist():
                assert forbidden_path_findings(name) == [], name

    def test_no_member_carries_a_secret(self) -> None:
        for name, text in packaged_bundles().items():
            assert secret_findings(name, text) == [], name

    def test_no_member_is_a_sqlite_database(self) -> None:
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            for name in bundle.namelist():
                head = bundle.read(name)[:16]
                assert not head.startswith(b"SQLite format 3"), name

    def test_bundles_contain_no_execution_primitive(self) -> None:
        for name, text in packaged_bundles().items():
            for token in FORBIDDEN_BUNDLE_TOKENS:
                assert token not in text, f"{token} in {name}"

    def test_bundles_declare_no_shell_or_terminal_surface(self) -> None:
        for name, text in packaged_bundles().items():
            lowered = text.lower()
            for token in ("child_process", "spawnsync", "shelljs", "node-pty"):
                assert token not in lowered, f"{token} in {name}"

    def test_packaged_manifest_requests_no_extra_permission(self) -> None:
        manifest = json.loads(packaged_bundles()["manifest.json"])
        assert sorted(manifest["permissions"]) == ["scripting", "storage"]
        assert not manifest.get("optional_permissions")
        for host in manifest["host_permissions"]:
            assert host.startswith(("https://chatgpt.com", "https://chat.openai.com", "http://127.0.0.1:8765"))


# -- Secret containment in the Bridge ----------------------------------------

class TestSecretNeverLeavesTheBridge:
    def test_endpoints_never_return_key_material(self, bridge) -> None:
        configure_openai(bridge)
        settings = bridge.client.get("/user/settings").text
        status = bridge.client.get("/provider/status").text
        probe = bridge.client.post("/provider/test", json={"provider": "openai"}).text
        for payload in (settings, status, probe):
            assert SAMPLE_API_KEY not in payload
            assert "sk-live-" not in payload
            assert "Authorization" not in payload
            assert "Bearer" not in payload
            assert "v1:" not in payload  # AES-256-GCM envelope prefix

    def test_audit_log_never_contains_the_key(self, bridge) -> None:
        configure_openai(bridge)
        bridge.client.post("/provider/test", json={"provider": "openai"})
        entries = json.dumps(bridge.audit_entries(), ensure_ascii=False)
        assert SAMPLE_API_KEY not in entries
        assert "sk-live-" not in entries
        assert "v1:" not in entries

    def test_plaintext_key_never_reaches_disk(self, bridge) -> None:
        configure_openai(bridge)
        workspace = bridge.projects_root.parent
        needle = SAMPLE_API_KEY.encode("utf-8")
        checked = 0
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            checked += 1
            assert needle not in path.read_bytes(), path
        assert checked > 0

    def test_failed_probe_reveals_no_vendor_detail(self, bridge) -> None:
        configure_openai(bridge)
        response = bridge.client.post(
            "/provider/test", json={"provider": "openai", "model": "gpt-4o"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["message"] in (
            "Connected",
            "Invalid API key",
            "Rate limit reached",
            "Provider unavailable",
            "Backend unreachable",
            "Not configured",
            "Provider rejected the request",
        )
        assert "Traceback" not in response.text
        assert str(REPO_ROOT) not in response.text


# -- Tool boundary -----------------------------------------------------------

class TestToolBoundaryAfterRelease:
    def test_backend_never_exposes_an_execution_capability(self) -> None:
        for capability in (
            "execute",
            "approve_from_chat",
            "apply_patch",
            "auto_fix",
            "auto_approve",
            "shell",
        ):
            assert capability in NEVER_AVAILABLE

    def test_extension_mirrors_the_same_forbidden_capabilities(self) -> None:
        source = (EXTENSION_DIR / "src" / "assistant" / "types.ts").read_text(encoding="utf-8")
        block = source.split("NEVER_AVAILABLE", 1)[1]
        for capability in NEVER_AVAILABLE:
            assert f'"{capability}"' in block, capability

    def test_chat_reports_tool_calls_as_unexecuted(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [{"role": "user", "content": "summarise the release"}],
                "provider": "local",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["toolCallsExecuted"] is False

    def test_provider_writes_stay_approval_gated(self) -> None:
        for action in RELEASE_WRITE_ACTIONS:
            assert level_for_action(action) == PermissionLevel.LEVEL_1, action

    def test_release_package_cannot_approve_or_execute(self) -> None:
        for source in sorted(RELEASE_PACKAGE.rglob("*.py")):
            text = source.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_TOOLING_CODE:
                assert forbidden not in text, f"{forbidden} in {source.name}"


# -- No auto approval --------------------------------------------------------

class TestNoAutoApproval:
    def test_provider_config_is_pending_until_a_human_approves(self, bridge) -> None:
        before = provider_entries(bridge)
        assert all(entry["hasStoredKey"] is False for entry in before.values())

        pending = bridge.client.post(
            "/provider/config",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": SAMPLE_API_KEY,
                "reason": "configure",
            },
        )
        assert pending.status_code == 202
        during = provider_entries(bridge)
        assert all(
            entry["hasStoredKey"] is False for entry in during.values()
        ), "activated without approval"

        assert bridge.approve(pending.json()["requestId"]).status_code == 200
        assert provider_entries(bridge)["openai"]["hasStoredKey"] is True

    def test_forget_is_also_approval_gated(self, bridge) -> None:
        configure_openai(bridge)
        pending = bridge.client.post(
            "/provider/forget", json={"provider": "openai", "reason": "forget"}
        )
        assert pending.status_code == 202
        assert provider_entries(bridge)["openai"]["hasStoredKey"] is True, "forgotten early"
        assert bridge.approve(pending.json()["requestId"]).status_code == 200
        assert provider_entries(bridge)["openai"]["hasStoredKey"] is False

    def test_phase8_approval_endpoint_still_exists(self, bridge) -> None:
        """§18: the release must not have removed the existing approval path."""
        response = bridge.client.post("/permission/approve", json={"request_id": "missing"})
        assert response.status_code in (400, 404, 409, 422)


# -- Release tooling is offline ----------------------------------------------

class TestReleaseToolingIsOffline:
    def test_auditors_import_no_network_client(self) -> None:
        for source in sorted(RELEASE_PACKAGE.rglob("*.py")):
            text = source.read_text(encoding="utf-8")
            for module in ("httpx", "requests", "urllib", "socket", "smtplib", "ftplib"):
                assert f"import {module}" not in text, f"{module} in {source.name}"

    def test_build_script_never_uploads_or_publishes(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        # Comments describing what the script does *not* do are fine; a command
        # invocation is not.
        commands = "\n".join(
            line for line in script.splitlines() if not line.lstrip().startswith("#")
        )
        for pattern in FORBIDDEN_SCRIPT_COMMANDS:
            assert re.search(pattern, commands) is None, pattern

    def test_build_script_writes_only_dist_and_the_archive(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        removals = re.findall(r"rm -[rf]+ ([^\n|;]+)", script)
        assert removals, "the clean step disappeared"
        for target in removals:
            assert "DIST_DIR" in target or "ARCHIVE" in target, target

    def test_release_docs_state_the_boundary_they_promise(self) -> None:
        """§7/§8: the docs must name the approval gate and the encrypted store."""
        install = (RELEASE_DIR / "INSTALL.md").read_text(encoding="utf-8")
        config = (RELEASE_DIR / "CONFIG.md").read_text(encoding="utf-8")
        for needle in ("202 pending", "ApprovalStore"):
            assert needle in install, needle
        for needle in ("AES-256-GCM", "chrome.storage", "202 pending"):
            assert needle in config, needle

    def test_encrypted_store_backs_the_documented_claim(self, bridge) -> None:
        """The CONFIG.md promise is only honest if the service reports the same."""
        settings = bridge.client.get("/user/settings").json()
        assert settings["keyStorage"]["algorithm"] == "AES-256-GCM"
        assert settings["readOnly"] is True
