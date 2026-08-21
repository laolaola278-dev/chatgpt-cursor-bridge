"""Phase 33 · Release packaging + audit.

This package holds the release-time auditors and the ZIP builder. The auditors
only ever *read*: a manifest file, a build directory, or a packaged ZIP. The
builder writes exactly one file — the release ZIP it is asked to produce — and
refuses to produce it at all when an audit finds something. Nothing here
uploads, publishes, executes or approves anything: ``release/build-release.sh``
drives the build and calls these functions, and the Phase 33 tests import the
same functions so the script and the test suite cannot drift apart.
"""

from .audit import (
    AuditReport,
    FORBIDDEN_PATH_RULES,
    REQUIRED_FILES,
    SECRET_RULES,
    audit_directory,
    audit_manifest,
    audit_manifest_file,
    audit_zip,
    run_audits,
)
from .package import (
    DEFAULT_ARCHIVE_NAME,
    PackageResult,
    build_release_zip,
    collect_members,
)

__all__ = [
    "AuditReport",
    "DEFAULT_ARCHIVE_NAME",
    "FORBIDDEN_PATH_RULES",
    "PackageResult",
    "REQUIRED_FILES",
    "SECRET_RULES",
    "audit_directory",
    "audit_manifest",
    "audit_manifest_file",
    "audit_zip",
    "build_release_zip",
    "collect_members",
    "run_audits",
]
