"""Phase 33 · Release & real-world validation tests.

Four groups, all of them offline:

* **Release artefacts** — `release/` exists, the build script drives the eight
  documented steps, the docs carry no real key, and the packaged ZIP contains
  exactly the three MV3 runtime files.
* **Release audit** — the auditors reject a package that carries a ``.env``, a
  value-shaped secret, a database, a test file or a source map, and they do *not*
  false-positive on the variable names the shipped code legitimately contains.
* **Provider validation** — configure / status / test, plus 401, 429, 5xx and a
  network failure, each through an injected ``httpx`` transport.
* **Conversation persistence** — the Phase 31/32 storage path still round-trips
  after the release work.

The auditors under test are the same functions ``release/build-release.sh``
calls, so the script and this suite cannot drift apart. Nothing here builds,
uploads, publishes or approves anything.
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

import httpx
import pytest

from app.assistant.crypto import SecretBox
from app.assistant.errors import (
    BACKEND_UNREACHABLE,
    CONNECTED_MESSAGE,
    INVALID_KEY,
    NOT_CONFIGURED_MESSAGE,
    PROVIDER_UNAVAILABLE,
    RATE_LIMITED,
    REQUEST_REJECTED,
    SAFE_MESSAGES,
)
from app.assistant.providers import provider_catalog
from app.assistant.providers import test_provider as probe_provider
from app.assistant.service import AssistantService
from app.assistant.store import AssistantSettingsStore
from app.llm_gateway.conversation import ConversationStore
from app.llm_gateway.models import MessageRole
from app.release import (
    REQUIRED_FILES,
    audit_directory,
    audit_manifest,
    audit_manifest_file,
    audit_zip,
    build_release_zip,
    collect_members,
)
from app.release.audit import forbidden_path_findings, secret_findings

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO_ROOT / "release"
EXTENSION_DIR = REPO_ROOT / "browser-extension"
RELEASE_ARCHIVE = RELEASE_DIR / "AI-Assistant-extension.zip"
BUILD_SCRIPT = RELEASE_DIR / "build-release.sh"
INSTALL_DOC = RELEASE_DIR / "INSTALL.md"
CONFIG_DOC = RELEASE_DIR / "CONFIG.md"
SOURCE_MANIFEST = EXTENSION_DIR / "manifest.json"

TEST_KEY = b"phase33-test-key-32-bytes-long!!"

# A key-shaped string that is deliberately *not* a real credential. It exists so
# the tests can prove the auditors catch a value-shaped secret; it is never sent
# anywhere and matches no provider account.
FAKE_KEY_VALUE = "sk-live-" + "0123456789abcdef0123456789"

MINIMAL_MANIFEST = {
    "manifest_version": 3,
    "name": "ChatGPT Cursor Bridge",
    "version": "0.2.0",
    "permissions": ["storage", "scripting"],
    "host_permissions": ["https://chatgpt.com/*", "http://127.0.0.1:8765/*"],
    "background": {"service_worker": "background/service-worker.js"},
    "content_scripts": [{"matches": ["https://chatgpt.com/*"], "js": ["content/content.js"]}],
}


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this module may reach a vendor endpoint, even by accident."""

    def blocked(self, request):  # noqa: ANN001, ANN202
        raise httpx.ConnectError("outbound network is disabled in tests", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)


@pytest.fixture
def clean_dist(tmp_path: Path) -> Path:
    """A synthetic build directory shaped exactly like a good ``dist/``."""
    root = tmp_path / "dist"
    (root / "content").mkdir(parents=True)
    (root / "background").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps(MINIMAL_MANIFEST), encoding="utf-8")
    # Variable names and masked hints are normal in shipped code: the auditors
    # must not treat any of these as a secret.
    (root / "content" / "content.js").write_text(
        'const body={api_key:input.apiKey};const env="OPENAI_API_KEY";const hint="****cdef";',
        encoding="utf-8",
    )
    (root / "background" / "service-worker.js").write_text(
        'const AUTH_HEADER_NAME="Authorization";// bearer tokens never live here\n',
        encoding="utf-8",
    )
    return root


def make_store() -> AssistantSettingsStore:
    """In-memory credential store with a fixed key: no disk, no environment."""
    return AssistantSettingsStore(":memory:", secret_box=SecretBox(key=TEST_KEY))


def configured_store(provider: str = "openai", model: str = "gpt-4o") -> AssistantSettingsStore:
    """Store with one *activated* credential, as a human approval would leave it."""
    store = make_store()
    staged = store.stage_credential(
        provider=provider, model=model, base_url="", api_key=FAKE_KEY_VALUE
    )
    store.activate_credential(staged.credential_id, approval_request_id="req_test")
    return store


def json_transport(status: int, payload: dict | None = None) -> httpx.MockTransport:
    body = payload if payload is not None else {"error": {"message": "org-1234 quota detail"}}
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


def ok_transport() -> httpx.MockTransport:
    return json_transport(
        200,
        {
            "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


def unreachable_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)

    return httpx.MockTransport(handler)


# -- Task 1 · release artefacts ---------------------------------------------

class TestReleaseArtefacts:
    def test_release_directory_holds_the_documented_files(self) -> None:
        assert RELEASE_DIR.is_dir()
        assert BUILD_SCRIPT.is_file()
        assert INSTALL_DOC.is_file()
        assert CONFIG_DOC.is_file()

    def test_build_script_fails_fast_and_calls_the_shared_auditors(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        assert "set -euo pipefail" in script
        # The rules must not be re-implemented in shell.
        assert "app.release audit" in script
        assert "app.release package" in script
        for step in (
            "Clean",
            "TypeScript Build",
            "MV3 Build",
            "Validate Manifest",
            "Validate Required Files",
            "Security Audit",
            "Generate ZIP",
            "Inspect ZIP",
        ):
            assert step in script, f"build step missing from the release script: {step}"

    def test_extension_exposes_a_release_script(self) -> None:
        package = json.loads((EXTENSION_DIR / "package.json").read_text(encoding="utf-8"))
        assert "release" in package["scripts"]
        assert "build-release.sh" in package["scripts"]["release"]

    def test_install_doc_covers_every_troubleshooting_case(self) -> None:
        text = INSTALL_DOC.read_text(encoding="utf-8")
        for phrase in (
            "Local Bridge unavailable",
            "Backend unreachable",
            "Not configured",
            "Invalid API key",
            "Rate limit reached",
            "Provider unavailable",
            "Streaming stopped",
            "Provider rejected the request",
            "chrome://extensions",
            "Load unpacked",
            "manifest.json",
        ):
            assert phrase in text, f"INSTALL.md does not document: {phrase}"

    def test_config_doc_states_the_api_key_guarantees(self) -> None:
        text = CONFIG_DOC.read_text(encoding="utf-8")
        for phrase in ("AES-256-GCM", "chrome.storage", "openai", "anthropic", "deepseek"):
            assert phrase in text, f"CONFIG.md does not document: {phrase}"

    def test_release_docs_contain_no_real_secret(self) -> None:
        """Documentation is audited with the same rules as the package (§13)."""
        for doc in (INSTALL_DOC, CONFIG_DOC, BUILD_SCRIPT):
            assert secret_findings(doc.name, doc.read_text(encoding="utf-8")) == []


# -- Task 2 · manifest audit -------------------------------------------------

class TestManifestAudit:
    def test_shipped_manifest_passes(self) -> None:
        report = audit_manifest_file(SOURCE_MANIFEST)
        assert report.ok, report.render()

    def test_all_urls_is_rejected(self) -> None:
        manifest = dict(MINIMAL_MANIFEST, host_permissions=["<all_urls>"])
        report = audit_manifest(manifest)
        assert not report.ok
        assert any("too broad" in finding for finding in report.findings)

    def test_wildcard_host_is_rejected(self) -> None:
        manifest = dict(MINIMAL_MANIFEST, host_permissions=["https://*/*"])
        assert not audit_manifest(manifest).ok

    def test_extra_permission_is_rejected(self) -> None:
        manifest = dict(MINIMAL_MANIFEST, permissions=["storage", "scripting", "tabs"])
        report = audit_manifest(manifest)
        assert any("unnecessary permission: tabs" in finding for finding in report.findings)

    def test_manifest_v2_is_rejected(self) -> None:
        assert not audit_manifest(dict(MINIMAL_MANIFEST, manifest_version=2)).ok

    def test_development_only_key_is_rejected(self) -> None:
        report = audit_manifest(dict(MINIMAL_MANIFEST, update_url="https://example.test/u.xml"))
        assert any("development-only" in finding for finding in report.findings)

    def test_missing_manifest_is_a_finding_not_a_crash(self, tmp_path: Path) -> None:
        report = audit_manifest_file(tmp_path / "manifest.json")
        assert report.findings == ["manifest.json is missing"]


# -- Task 3 · build-directory audit -----------------------------------------

class TestBuildDirectoryAudit:
    def test_clean_directory_passes(self, clean_dist: Path) -> None:
        report = audit_directory(clean_dist)
        assert report.ok, report.render()
        assert report.entries == sorted(REQUIRED_FILES)

    def test_variable_names_are_not_secrets(self, clean_dist: Path) -> None:
        """The whole point of §5: an identifier is not a credential."""
        text = (clean_dist / "content" / "content.js").read_text(encoding="utf-8")
        assert "OPENAI_API_KEY" in text
        assert secret_findings("content/content.js", text) == []

    def test_missing_runtime_file_is_a_finding(self, clean_dist: Path) -> None:
        (clean_dist / "background" / "service-worker.js").unlink()
        report = audit_directory(clean_dist)
        assert any("background/service-worker.js" in finding for finding in report.findings)

    @pytest.mark.parametrize(
        ("relative", "label"),
        [
            (".env", "env file"),
            ("content/content.js.map", "source map"),
            ("src/main.ts", "source code"),
            ("tests/smoke.test.js", "test file"),
            ("data/bridge.sqlite3", "sqlite database"),
            ("workspace/demo/notes.txt", "workspace data"),
            ("package.json", "development config"),
            ("debug.log", "debug log"),
            ("node_modules/dep/index.js", "dependency tree"),
        ],
    )
    def test_forbidden_file_is_rejected(self, clean_dist: Path, relative: str, label: str) -> None:
        target = clean_dist / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder", encoding="utf-8")
        report = audit_directory(clean_dist)
        assert not report.ok
        assert any(finding.startswith(label) for finding in report.findings), report.findings

    def test_value_shaped_secret_is_rejected(self, clean_dist: Path) -> None:
        (clean_dist / "content" / "content.js").write_text(
            f'const key = "{FAKE_KEY_VALUE}";', encoding="utf-8"
        )
        report = audit_directory(clean_dist)
        assert not report.ok
        assert any("style key" in finding for finding in report.findings)

    def test_findings_never_echo_the_secret_value(self, clean_dist: Path) -> None:
        (clean_dist / "content" / "content.js").write_text(
            f"OPENAI_API_KEY={FAKE_KEY_VALUE}", encoding="utf-8"
        )
        report = audit_directory(clean_dist)
        assert not report.ok
        rendered = report.render() + json.dumps(report.as_dict())
        assert FAKE_KEY_VALUE not in rendered
        assert "sk-live-" not in rendered

    def test_bearer_token_is_rejected(self, clean_dist: Path) -> None:
        (clean_dist / "background" / "service-worker.js").write_text(
            'headers.set("Authorization", "Bearer abcdefghijklmnopqrstuvwxyz");', encoding="utf-8"
        )
        assert not audit_directory(clean_dist).ok

    def test_missing_directory_is_a_finding(self, tmp_path: Path) -> None:
        report = audit_directory(tmp_path / "absent")
        assert report.findings == ["build directory does not exist"]

    def test_forbidden_path_rules_normalise_windows_separators(self) -> None:
        assert forbidden_path_findings("src\\main.ts")

    def test_dot_prefixed_names_are_not_stripped_into_innocence(self) -> None:
        """A root-level `.env` must stay a `.env`, however the archive spells it."""
        for spelling in (".env", "./.env", ".env.local", "./config/.env"):
            assert forbidden_path_findings(spelling), spelling


# -- Task 4 · packaging ------------------------------------------------------

class TestPackaging:
    def test_packaging_a_clean_directory_produces_an_audited_zip(
        self, clean_dist: Path, tmp_path: Path
    ) -> None:
        archive = tmp_path / "out" / "AI-Assistant-extension.zip"
        result = build_release_zip(clean_dist, archive)
        assert result.ok, result.render()
        assert archive.is_file()
        with zipfile.ZipFile(archive) as bundle:
            assert sorted(bundle.namelist()) == sorted(REQUIRED_FILES)

    def test_packaging_refuses_a_dirty_directory(self, clean_dist: Path, tmp_path: Path) -> None:
        (clean_dist / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY_VALUE}\n", encoding="utf-8")
        archive = tmp_path / "dirty.zip"
        result = build_release_zip(clean_dist, archive)
        assert not result.ok
        assert not archive.exists(), "an unsafe archive must never be left on disk"
        assert FAKE_KEY_VALUE not in json.dumps(result.as_dict())

    def test_packaging_refuses_an_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = build_release_zip(empty, tmp_path / "empty.zip")
        assert not result.ok

    def test_editor_artefacts_are_skipped(self, clean_dist: Path, tmp_path: Path) -> None:
        (clean_dist / ".DS_Store").write_text("junk", encoding="utf-8")
        members = collect_members(clean_dist)
        assert ".DS_Store" not in members
        assert build_release_zip(clean_dist, tmp_path / "clean.zip").ok

    def test_no_partial_archive_survives_a_refusal(self, clean_dist: Path, tmp_path: Path) -> None:
        (clean_dist / "content" / "content.js.map").write_text("{}", encoding="utf-8")
        archive = tmp_path / "refused.zip"
        assert not build_release_zip(clean_dist, archive).ok
        assert list(tmp_path.glob("refused.zip*")) == []


# -- Task 5 · the archive that actually ships ---------------------------------

class TestReleaseArchive:
    """Audits `release/AI-Assistant-extension.zip` itself, not a synthetic one."""

    @pytest.fixture(autouse=True)
    def require_archive(self) -> None:
        if not RELEASE_ARCHIVE.is_file():
            pytest.skip("release archive not built yet: run release/build-release.sh")

    def test_archive_passes_the_release_audit(self) -> None:
        report = audit_zip(RELEASE_ARCHIVE)
        assert report.ok, report.render()

    def test_archive_holds_exactly_the_three_runtime_files(self) -> None:
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            names = sorted(i.filename for i in bundle.infolist() if not i.is_dir())
        assert names == sorted(REQUIRED_FILES)

    def test_archive_carries_no_forbidden_path(self) -> None:
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            for name in bundle.namelist():
                assert forbidden_path_findings(name) == [], name

    def test_archive_carries_no_secret(self) -> None:
        """§4/§5: no .env, key, secret, database, workspace file, test or map."""
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            for name in bundle.namelist():
                text = bundle.read(name).decode("utf-8", errors="replace")
                assert secret_findings(name, text) == [], name

    def test_archive_manifest_is_minimal(self) -> None:
        with zipfile.ZipFile(RELEASE_ARCHIVE) as bundle:
            packaged = json.loads(bundle.read("manifest.json").decode("utf-8"))
        assert packaged["manifest_version"] == 3
        assert sorted(packaged["permissions"]) == ["scripting", "storage"]
        for host in packaged["host_permissions"]:
            assert "*://" not in host and host != "<all_urls>"
        assert audit_manifest(packaged).ok


# -- Task 6 · provider configuration, status and connection test -------------

class TestProviderValidation:
    """§10/§22: configure, status, test, 401, 429, 5xx and a network failure."""

    def test_local_provider_is_connected_without_a_key(self) -> None:
        outcome = probe_provider(make_store(), provider="local")
        assert outcome.status == "connected"
        assert outcome.message == CONNECTED_MESSAGE

    def test_unconfigured_vendor_is_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(env, raising=False)
        outcome = probe_provider(make_store(), provider="openai")
        assert outcome.status == "not_configured"
        assert outcome.message == NOT_CONFIGURED_MESSAGE

    def test_configured_provider_reports_connected(self) -> None:
        outcome = probe_provider(
            configured_store(), provider="openai", model="gpt-4o", transport=ok_transport()
        )
        assert outcome.status == "connected"
        assert outcome.message == CONNECTED_MESSAGE

    def test_status_list_covers_the_three_vendors_and_leaks_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(env, raising=False)
        catalog = provider_catalog(configured_store(), transport=ok_transport())
        by_name = {entry["provider"]: entry for entry in catalog}
        assert {"openai", "anthropic", "deepseek", "local"} <= set(by_name)
        assert by_name["openai"]["hasStoredKey"] is True
        assert by_name["anthropic"]["status"] == "not_configured"
        rendered = json.dumps(catalog)
        assert FAKE_KEY_VALUE not in rendered
        assert "sk-live-" not in rendered
        assert "authorization" not in rendered.lower()
        # Only the masked tail may be shown for a stored key.
        assert by_name["openai"]["keyHint"].startswith("****")

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, INVALID_KEY),
            (403, INVALID_KEY),
            (429, RATE_LIMITED),
            (500, PROVIDER_UNAVAILABLE),
            (503, PROVIDER_UNAVAILABLE),
            (400, REQUEST_REJECTED),
        ],
    )
    def test_http_failures_map_to_the_safe_vocabulary(self, status: int, expected: str) -> None:
        outcome = probe_provider(
            configured_store(),
            provider="openai",
            model="gpt-4o",
            transport=json_transport(status),
        )
        assert outcome.status == "failed"
        assert outcome.message == expected
        assert outcome.message in SAFE_MESSAGES

    def test_network_failure_maps_to_backend_unreachable(self) -> None:
        outcome = probe_provider(
            configured_store(),
            provider="openai",
            model="gpt-4o",
            transport=unreachable_transport(),
        )
        assert outcome.status == "failed"
        assert outcome.message == BACKEND_UNREACHABLE

    @pytest.mark.parametrize("status", [401, 429, 500])
    def test_failure_never_echoes_the_vendor_body_or_the_key(self, status: int) -> None:
        """§13: not even a failing test may surface provider text or key material."""
        outcome = probe_provider(
            configured_store(),
            provider="openai",
            model="gpt-4o",
            transport=json_transport(status),
        )
        rendered = json.dumps(outcome.as_dict())
        assert "org-1234" not in rendered  # the injected vendor detail
        assert FAKE_KEY_VALUE not in rendered
        assert "Bearer" not in rendered

    def test_status_is_recorded_for_the_settings_page(self) -> None:
        store = configured_store()
        probe_provider(
            store, provider="openai", model="gpt-4o", transport=json_transport(401)
        )
        record = store.active_credential("openai")
        assert record is not None
        assert record.connection_status == "failed"


# -- Task 7 · the release surface of the assistant service -------------------

class TestReleaseServiceSurface:
    def test_settings_payload_carries_no_key_material(self) -> None:
        """§8/§10: the settings payload may say a key exists, never what it is."""
        service = AssistantService(configured_store(), transport=ok_transport())
        payload = json.dumps(service.user_settings())
        lowered = payload.lower()
        for forbidden in ("api_key", "apikey", "authorization", "secret", "bearer"):
            assert forbidden not in lowered, forbidden
        assert FAKE_KEY_VALUE not in payload
        assert "AES-256-GCM" in payload

    def test_user_mode_is_the_default_surface(self) -> None:
        service = AssistantService(make_store(), transport=ok_transport())
        settings = service.user_settings()
        assert settings["mode"] == "user"
        surfaces = " ".join(settings["surfaces"]).lower()
        for advanced in ("governance", "intelligence", "graph", "metrics"):
            assert advanced not in surfaces, advanced

    def test_execution_capabilities_are_never_available(self) -> None:
        service = AssistantService(make_store(), transport=ok_transport())
        never = service.user_settings()["neverAvailable"]
        for capability in ("execute", "approve_from_chat", "apply_patch", "auto_fix", "shell"):
            assert capability in never

    def test_provider_test_through_the_service_stays_in_the_vocabulary(self) -> None:
        service = AssistantService(configured_store(), transport=json_transport(429))
        result = service.test_provider(provider="openai", model="gpt-4o")
        assert result["message"] == RATE_LIMITED
        assert result["readOnly"] is True


# -- Task 8 · conversation persistence survives the release work -------------

class TestConversationPersistence:
    def test_conversation_round_trips_after_a_reload(self, tmp_path: Path) -> None:
        """§15: create -> send -> assistant reply -> reload -> continue."""
        db = tmp_path / "conversations.sqlite3"
        store = ConversationStore(db)
        conversation = store.create_conversation(
            project="release-check", provider="openai", model="gpt-4o", title="Release check"
        )
        store.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content="does the packaged build still store history?",
        )
        store.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.ASSISTANT,
            content="yes, storage is untouched by the release work",
        )

        # A fresh store stands in for restarting the Bridge / reopening the panel.
        reopened = ConversationStore(db)
        again = reopened.get_conversation(conversation.conversation_id, "release-check")
        assert again is not None
        assert (again.provider, again.model) == ("openai", "gpt-4o")
        assert again.title == "Release check"

        messages = reopened.list_messages(conversation.conversation_id)
        assert len(messages) == 2
        assert {message.role for message in messages} == {
            MessageRole.USER,
            MessageRole.ASSISTANT,
        }

        # Continuing the conversation after the reload appends, never replaces.
        reopened.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content="continue",
        )
        assert len(reopened.list_messages(conversation.conversation_id)) == 3
        assert reopened.list_conversations("release-check")[0].conversation_id == (
            conversation.conversation_id
        )

    def test_conversations_stay_project_isolated(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conversations.sqlite3")
        mine = store.create_conversation(
            project="alpha", provider="local", model="local/simulator-v1", title="alpha"
        )
        assert store.get_conversation(mine.conversation_id, "beta") is None
        assert store.list_conversations("beta") == []


# -- §11: the real-provider suite must default to SKIP ------------------------

class TestRealProviderSuiteIsOptIn:
    """The optional real-GPT tests exist, and a plain ``pytest -q`` skips them."""

    real_dir = Path(__file__).resolve().parent / "real"

    def test_the_real_suite_exists(self) -> None:
        assert (self.real_dir / "__init__.py").is_file()
        assert (self.real_dir / "test_phase33_openai_real.py").is_file()

    def test_both_environment_gates_are_required(self, monkeypatch) -> None:
        from real import real_run_enabled

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("REAL_LLM_RUN", raising=False)
        assert real_run_enabled() is False, "no gate set"

        monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key-000000000000")
        assert real_run_enabled() is False, "a key alone must not enable real runs"

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("REAL_LLM_RUN", "1")
        assert real_run_enabled() is False, "the flag alone must not enable real runs"

        monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key-000000000000")
        assert real_run_enabled() is True, "both gates set must enable real runs"

    def test_the_module_is_gated_and_carries_no_credential(self) -> None:
        source = (self.real_dir / "test_phase33_openai_real.py").read_text(encoding="utf-8")
        assert "pytestmark = pytest.mark.skipif(not real_run_enabled()" in source
        # §13: no key-shaped literal, and no print of a key or a header.
        assert re.search(r"sk-(?:live|proj|ant)-[A-Za-z0-9]{16,}", source) is None
        assert re.search(r"(?<![A-Za-z_])print\(", source) is None
        assert secret_findings("test_phase33_openai_real.py", source) == []

    def test_the_real_suite_reports_only_skips_by_default(self) -> None:
        """Collected, gated, and never executed without the opt-in."""
        import importlib

        module = importlib.import_module("real.test_phase33_openai_real")
        marker = module.pytestmark
        assert marker.name == "skipif"
        # Without both env gates the condition is truthy => every test skips.
        assert marker.args[0] is True or os.environ.get("REAL_LLM_RUN") == "1"






