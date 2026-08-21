"""Phase 29 · Advanced Developer Context & Read-only Code Intelligence.

Read-only developer context bundles for the AI assistant: project, file,
symbol, dependency, git and test/build context with explicit budgets and
security filtering. Nothing here executes, mutates source, or enqueues
approvals.
"""

from .budget import ContextBudget, DEFAULT_MAX_BUNDLE_BYTES, DEFAULT_MAX_DEPENDENCIES, DEFAULT_MAX_DIFF_BYTES, DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_FILES, DEFAULT_MAX_SYMBOLS
from .bundle import ContextBundleEngine
from .models import (
    DevContextBundle,
    DevDependencyContext,
    DevFileContext,
    DevGitContext,
    DevProjectContext,
    DevSymbolContext,
    DevTestBuildContext,
)
from .security import is_sensitive_path, redact_secrets

__all__ = [
    "ContextBudget",
    "ContextBundleEngine",
    "DEFAULT_MAX_BUNDLE_BYTES",
    "DEFAULT_MAX_DEPENDENCIES",
    "DEFAULT_MAX_DIFF_BYTES",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_SYMBOLS",
    "DevContextBundle",
    "DevDependencyContext",
    "DevFileContext",
    "DevGitContext",
    "DevProjectContext",
    "DevSymbolContext",
    "DevTestBuildContext",
    "is_sensitive_path",
    "redact_secrets",
]
