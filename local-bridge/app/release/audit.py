"""Phase 33 · Release ZIP / build-directory / manifest auditors.

Read-only checks that run before a release is published:

* the package contains exactly the runtime files the extension needs,
* it contains no ``.env``, secret, database, workspace file, test or source map,
* the MV3 manifest is minimal (no ``<all_urls>``, no development-only keys).

Secret detection deliberately separates a **variable name** from a **real
value**: ``api_key: input.apiKey`` and the string ``OPENAI_API_KEY`` are normal
parts of the shipped code, while ``OPENAI_API_KEY=sk-live-…`` is a finding. Every
rule therefore requires a value-shaped token, never a bare identifier.

Nothing in this module writes, uploads, executes or approves anything.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Runtime files the MV3 extension cannot start without.
REQUIRED_FILES = ("manifest.json", "content/content.js", "background/service-worker.js")

# Files that must never travel inside a release package (label, path regex).
FORBIDDEN_PATH_RULES = (
    ("env file", r"(^|/)\.env(\.|$)"),
    ("source map", r"\.map$"),
    ("source code", r"\.(ts|tsx|jsx|py|pyc|pyo)$"),
    ("source directory", r"(^|/)src/"),
    ("test file", r"(^|/)(tests?|__tests__)/|\.test\.|\.spec\."),
    ("sqlite database", r"\.(db|sqlite|sqlite3)$"),
    ("workspace data", r"(^|/)workspace/"),
    ("dependency tree", r"(^|/)node_modules/"),
    (
        "development config",
        r"(^|/)(vite\.config|vitest\.config|tsconfig|package\.json|package-lock\.json"
        r"|eslint\.config|postcss\.config|next\.config|\.gitignore|requirements\.txt|pytest\.ini)",
    ),
    ("debug log", r"\.log$"),
)

# Value-shaped secret patterns. A bare identifier never matches.
SECRET_RULES = (
    ("openai/anthropic style key", r"\bsk-(?:proj-|ant-|live-)?[A-Za-z0-9_-]{16,}"),
    (
        "provider key assignment",
        r"(?i)(?:OPENAI|ANTHROPIC|DEEPSEEK)_API_KEY\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}",
    ),
    (
        "authorization value",
        r"(?i)\bauthorization\b\s*[:=]\s*[\"']?(?:bearer\s+)?[A-Za-z0-9._\-]{16,}",
    ),
    ("bearer token", r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    (
        "dotenv secret assignment",
        r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z0-9_]*\s*=\s*\S{8,}\s*$",
    ),
)

# Permissions the release is allowed to request (spec §6: minimal).
ALLOWED_PERMISSIONS = {"storage", "scripting"}
# Host permission shapes that are never acceptable in a release.
FORBIDDEN_HOSTS = ("<all_urls>", "*://*/*", "http://*/*", "https://*/*")
# Manifest keys that only make sense during development.
DEV_ONLY_MANIFEST_KEYS = ("key", "update_url", "devtools_page", "externally_connectable")

# Extensions worth scanning for secret text; binaries are listed but not read.
TEXT_SUFFIXES = {".js", ".json", ".html", ".css", ".txt", ".md", ".map", ".env", ""}
MAX_SCAN_BYTES = 4_000_000


@dataclass
class AuditReport:
    """Outcome of one read-only audit.

    ``findings`` is the only thing that decides success: an empty list means the
    package may be released, anything else must fail the build with a non-zero
    exit code. ``entries`` is informational so the release log can show what was
    actually inspected.
    """

    target: str
    kind: str
    findings: list[str] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, finding: str) -> None:
        self.findings.append(finding)

    def extend(self, findings: list[str]) -> None:
        self.findings.extend(findings)

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "kind": self.kind,
            "ok": self.ok,
            "findings": list(self.findings),
            "entries": list(self.entries),
        }

    def render(self) -> str:
        head = f"{'PASS' if self.ok else 'FAIL'} {self.kind}: {self.target}"
        if self.ok:
            return f"{head} ({len(self.entries)} entries)"
        lines = [head] + [f"  - {item}" for item in self.findings]
        return "\n".join(lines)


def forbidden_path_findings(name: str) -> list[str]:
    """Return one finding per forbidden-path rule the archive member matches."""

    # ``lstrip("./")`` would strip *characters*, turning a root-level ``.env``
    # into ``env`` and letting it slip past the rules. Only the ``./`` prefix
    # zipfile sometimes records may be removed.
    normalized = name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    return [
        f"{label}: {normalized}"
        for label, pattern in FORBIDDEN_PATH_RULES
        if re.search(pattern, normalized, re.IGNORECASE)
    ]


def secret_findings(name: str, text: str) -> list[str]:
    """Return findings for value-shaped secrets inside ``text``.

    Only the rule label and the location are reported — the matched value is
    never echoed, so an audit log can never become the leak it is looking for.
    """

    findings: list[str] = []
    for label, pattern in SECRET_RULES:
        match = re.search(pattern, text)
        if match is None:
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append(f"{label} in {name}:{line}")
    return findings


def _is_text_member(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_SUFFIXES


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def audit_manifest(manifest: dict, *, target: str = "manifest.json") -> AuditReport:
    """Check an already-parsed MV3 manifest against the release rules (§6)."""

    report = AuditReport(target=target, kind="manifest")
    report.entries = sorted(manifest.keys())

    if manifest.get("manifest_version") != 3:
        report.add(f"manifest_version must be 3, found {manifest.get('manifest_version')!r}")

    worker = (manifest.get("background") or {}).get("service_worker")
    if worker != "background/service-worker.js":
        report.add(f"background.service_worker must be background/service-worker.js, found {worker!r}")

    scripts = manifest.get("content_scripts") or []
    if not scripts:
        report.add("content_scripts is missing")
    else:
        declared: list[str] = []
        for entry in scripts:
            declared.extend(entry.get("js") or [])
            for match in entry.get("matches") or []:
                if match in FORBIDDEN_HOSTS:
                    report.add(f"content script match is too broad: {match}")
        if "content/content.js" not in declared:
            report.add(f"content script must load content/content.js, found {declared!r}")

    for permission in manifest.get("permissions") or []:
        if permission not in ALLOWED_PERMISSIONS:
            report.add(f"unnecessary permission: {permission}")

    hosts = manifest.get("host_permissions") or []
    if not hosts:
        report.add("host_permissions is missing")
    for host in hosts:
        if host in FORBIDDEN_HOSTS or "://*/*" in host:
            report.add(f"host permission is too broad: {host}")

    if manifest.get("optional_permissions"):
        report.add("optional_permissions must be empty in a release")

    for key in DEV_ONLY_MANIFEST_KEYS:
        if key in manifest:
            report.add(f"development-only manifest key: {key}")

    csp = manifest.get("content_security_policy") or {}
    csp_text = json.dumps(csp) if isinstance(csp, dict) else str(csp)
    for unsafe in ("unsafe-eval", "unsafe-inline"):
        if unsafe in csp_text:
            report.add(f"content_security_policy allows {unsafe}")

    report.extend(secret_findings(target, json.dumps(manifest)))
    return report


def audit_manifest_file(path: str | Path) -> AuditReport:
    """Parse ``path`` and audit it. An unreadable manifest is itself a finding."""

    manifest_path = Path(path)
    if not manifest_path.is_file():
        return AuditReport(
            target=str(manifest_path), kind="manifest", findings=["manifest.json is missing"]
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return AuditReport(
            target=str(manifest_path),
            kind="manifest",
            findings=[f"manifest.json is not valid JSON: {exc.__class__.__name__}"],
        )
    if not isinstance(manifest, dict):
        return AuditReport(
            target=str(manifest_path), kind="manifest", findings=["manifest.json is not an object"]
        )
    return audit_manifest(manifest, target=str(manifest_path))


def _audit_members(
    report: AuditReport,
    names: list[str],
    read: Callable[[str], bytes | None],
) -> AuditReport:
    """Shared body for the directory and ZIP auditors."""

    report.entries = sorted(names)

    for required in REQUIRED_FILES:
        if required not in report.entries:
            report.add(f"required runtime file is missing: {required}")

    for name in report.entries:
        report.extend(forbidden_path_findings(name))
        if not _is_text_member(name):
            continue
        data = read(name)
        if data is None or len(data) > MAX_SCAN_BYTES:
            continue
        report.extend(secret_findings(name, _decode(data)))

    return report


def audit_directory(path: str | Path) -> AuditReport:
    """Audit an unpacked build directory (``browser-extension/dist``)."""

    root = Path(path)
    report = AuditReport(target=str(root), kind="build directory")
    if not root.is_dir():
        report.add("build directory does not exist")
        return report

    files = [item for item in root.rglob("*") if item.is_file()]
    names = [item.relative_to(root).as_posix() for item in files]

    def read(name: str) -> bytes | None:
        try:
            return (root / name).read_bytes()
        except OSError:
            return None

    _audit_members(report, names, read)
    manifest = root / "manifest.json"
    if manifest.is_file():
        report.extend(audit_manifest_file(manifest).findings)
    return report


def audit_zip(path: str | Path) -> AuditReport:
    """Audit a packaged release ZIP without extracting it."""

    archive_path = Path(path)
    report = AuditReport(target=str(archive_path), kind="release zip")
    if not archive_path.is_file():
        report.add("release zip does not exist")
        return report

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            names = [info.filename.replace("\\", "/") for info in infos]

            def read(name: str) -> bytes | None:
                try:
                    with archive.open(name) as handle:
                        return handle.read(MAX_SCAN_BYTES + 1)
                except (KeyError, OSError, zipfile.BadZipFile):
                    return None

            _audit_members(report, names, read)
            if "manifest.json" in report.entries:
                data = read("manifest.json")
                try:
                    manifest = json.loads(_decode(data or b""))
                except json.JSONDecodeError:
                    report.add("manifest.json inside the zip is not valid JSON")
                else:
                    if isinstance(manifest, dict):
                        report.extend(
                            audit_manifest(manifest, target="manifest.json (zip)").findings
                        )
                    else:
                        report.add("manifest.json inside the zip is not an object")
    except zipfile.BadZipFile:
        report.add("release zip is not a valid archive")
    return report


# -- CLI ------------------------------------------------------------------
#
# ``release/build-release.sh`` calls this entry point instead of re-implementing
# the rules in shell, so the script, the auditors and the Phase 33 tests all
# agree by construction. The CLI only reads: it never writes, packages or
# publishes anything, and a single finding is enough to fail the build.


def run_audits(
    *,
    manifest: str | Path | None = None,
    directory: str | Path | None = None,
    archive: str | Path | None = None,
) -> list[AuditReport]:
    """Run every requested auditor and return the reports in call order."""

    reports: list[AuditReport] = []
    if manifest is not None:
        reports.append(audit_manifest_file(manifest))
    if directory is not None:
        reports.append(audit_directory(directory))
    if archive is not None:
        reports.append(audit_zip(archive))
    return reports


def main(argv: list[str] | None = None) -> int:
    """Audit a manifest, a build directory and/or a ZIP. Non-zero on findings."""

    parser = argparse.ArgumentParser(
        prog="python -m app.release.audit",
        description="Read-only Phase 33 release audit (manifest / build directory / zip).",
    )
    parser.add_argument("--manifest", help="path to manifest.json")
    parser.add_argument("--dir", dest="directory", help="path to the built extension directory")
    parser.add_argument("--zip", dest="archive", help="path to the release zip")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--list-entries", action="store_true", help="also print every inspected entry"
    )
    args = parser.parse_args(argv)

    if not (args.manifest or args.directory or args.archive):
        parser.error("choose at least one of --manifest, --dir, --zip")

    reports = run_audits(
        manifest=args.manifest, directory=args.directory, archive=args.archive
    )
    ok = all(report.ok for report in reports)

    if args.json:
        print(json.dumps({"ok": ok, "reports": [r.as_dict() for r in reports]}, indent=2))
    else:
        for report in reports:
            print(report.render())
            if args.list_entries:
                for entry in report.entries:
                    print(f"    {entry}")
        print("release audit: PASS" if ok else "release audit: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the release script
    sys.exit(main())
