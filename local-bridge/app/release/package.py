"""Phase 33 · Release ZIP builder.

Packages the already-built MV3 extension directory into
``release/AI-Assistant-extension.zip``. The builder is deliberately narrow:

* it only reads from the build directory and only writes the one ZIP path it is
  given — no publishing, no uploading, no network access at all,
* it refuses to package anything that fails :mod:`app.release.audit`, so a
  package containing a ``.env``, a secret, a database, a test or a source map can
  never be produced in the first place,
* it uses :mod:`zipfile` rather than an external ``zip`` binary so the same
  command works on Windows, macOS and Linux.

``stdlib only`` is a hard requirement here: the release script must run on a
machine that has not installed the Bridge's Python dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .audit import AuditReport, audit_directory, audit_zip

DEFAULT_ARCHIVE_NAME = "AI-Assistant-extension.zip"
# Anything matching these is dropped before packaging even starts. The audit
# would catch them anyway; skipping them keeps a stray editor artefact from
# turning a clean build into a failed release.
SKIP_NAMES = (".DS_Store", "Thumbs.db", "desktop.ini")
SKIP_SUFFIXES = (".map", ".log", ".ts", ".tsx")


@dataclass
class PackageResult:
    """Outcome of one packaging attempt."""

    archive: str
    created: bool
    members: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    reports: list[AuditReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.created and not self.findings

    def as_dict(self) -> dict:
        return {
            "archive": self.archive,
            "created": self.created,
            "ok": self.ok,
            "members": list(self.members),
            "findings": list(self.findings),
            "reports": [report.as_dict() for report in self.reports],
        }

    def render(self) -> str:
        head = f"{'PASS' if self.ok else 'FAIL'} release package: {self.archive}"
        if self.ok:
            return f"{head} ({len(self.members)} files)"
        return "\n".join([head] + [f"  - {item}" for item in self.findings])


def _should_skip(relative: str) -> bool:
    name = relative.rsplit("/", 1)[-1]
    if name in SKIP_NAMES:
        return True
    return relative.endswith(SKIP_SUFFIXES)


def collect_members(source: str | Path) -> list[str]:
    """Return the packageable files of ``source``, as sorted posix paths."""

    root = Path(source)
    if not root.is_dir():
        return []
    names = [
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file()
    ]
    return sorted(name for name in names if not _should_skip(name))


def build_release_zip(
    source: str | Path,
    archive: str | Path,
    *,
    audit_first: bool = True,
) -> PackageResult:
    """Zip ``source`` into ``archive``, refusing to write an unsafe package.

    The build directory is audited *before* the ZIP is created and the finished
    ZIP is audited again afterwards; both reports travel back in the result so
    the release log shows exactly what was checked.
    """

    root = Path(source)
    target = Path(archive)
    result = PackageResult(archive=str(target), created=False)

    if not root.is_dir():
        result.findings.append(f"build directory does not exist: {root}")
        return result

    if audit_first:
        pre = audit_directory(root)
        result.reports.append(pre)
        if not pre.ok:
            result.findings.extend(pre.findings)
            return result

    members = collect_members(root)
    if not members:
        result.findings.append(f"build directory is empty: {root}")
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    # Written to a temporary name first: an interrupted run must not leave a
    # half-written archive behind that a later step would happily publish.
    staging = target.with_suffix(target.suffix + ".partial")
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in members:
                bundle.write(root / name, arcname=name)
        staging.replace(target)
    except OSError as exc:
        staging.unlink(missing_ok=True)
        result.findings.append(f"could not write the release zip: {exc.__class__.__name__}")
        return result

    result.created = True
    result.members = members

    post = audit_zip(target)
    result.reports.append(post)
    if not post.ok:
        # An unsafe archive is removed rather than left on disk to be shipped.
        target.unlink(missing_ok=True)
        result.created = False
        result.findings.extend(post.findings)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI used by ``release/build-release.sh``. Non-zero on any finding."""

    parser = argparse.ArgumentParser(
        prog="python -m app.release.package",
        description="Package the built MV3 extension into the Phase 33 release ZIP.",
    )
    parser.add_argument("--source", required=True, help="built extension directory (dist)")
    parser.add_argument("--output", required=True, help="path of the release zip to write")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--no-audit", action="store_true", help="skip the pre-package audit (not for releases)"
    )
    args = parser.parse_args(argv)

    result = build_release_zip(args.source, args.output, audit_first=not args.no_audit)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        for report in result.reports:
            print(report.render())
        print(result.render())
        for name in result.members:
            print(f"    {name}")
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the release script
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_NAME",
    "PackageResult",
    "build_release_zip",
    "collect_members",
]
