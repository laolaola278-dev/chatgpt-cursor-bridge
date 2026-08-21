"""Read-only dependency context.

Parses common manifest files (package.json, requirements.txt, pyproject.toml,
Cargo.toml, go.mod, pom.xml, Gemfile, build.gradle) purely as text. It never
installs, upgrades or mutates anything and never runs a package manager.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import Settings
from app.security.sandbox import get_project_dir

from .budget import ContextBudget
from .security import is_sensitive_path

MANIFEST_NAMES = (
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "Gemfile",
    "build.gradle",
    "build.gradle.kts",
)

_VERSION_RE = re.compile(r"([0-9]+(?:\.[0-9A-Za-z_-]+)*)")


class DependencyContextService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(self, project: str, budget: ContextBudget) -> dict[str, Any]:
        root = get_project_dir(project, self._settings)
        dependencies: list[dict[str, Any]] = []
        manifests: list[dict[str, Any]] = []
        scanned = 0
        for relative in self._find_manifests(root, budget.max_manifest_files):
            if is_sensitive_path(relative):
                continue
            scanned += 1
            path = root / Path(*relative.split("/"))
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            source = str(relative)
            if path.name == "package.json":
                parsed = self._parse_package_json(text, source)
            elif path.name == "requirements.txt":
                parsed = self._parse_requirements(text, source)
            elif path.name == "pyproject.toml":
                parsed = self._parse_pyproject(text, source)
            elif path.name == "Cargo.toml":
                parsed = self._parse_cargo(text, source)
            elif path.name == "go.mod":
                parsed = self._parse_go_mod(text, source)
            elif path.name in {"pom.xml", "build.gradle", "build.gradle.kts", "Gemfile"}:
                parsed = self._parse_generic(text, source)
            else:  # pragma: no cover - defensive
                parsed = ([], source, [])
            entries, manifest_source, managers = parsed
            manifests.append({"source": manifest_source, "count": len(entries), "managers": managers})
            dependencies.extend(entries)
            if len(dependencies) >= budget.max_dependencies:
                break
        truncated = len(dependencies) > budget.max_dependencies or scanned > budget.max_manifest_files
        return {
            "dependencies": dependencies[: budget.max_dependencies],
            "total": len(dependencies),
            "truncated": truncated,
            "manifests": manifests,
        }

    def _find_manifests(self, root: Path, limit: int) -> list[str]:
        found: list[str] = []
        for name in MANIFEST_NAMES:
            for path in sorted(root.rglob(name)):
                if any(part in {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"} for part in path.relative_to(root).parts):
                    continue
                found.append(path.relative_to(root).as_posix())
                if len(found) >= limit:
                    return found
        return found

    @staticmethod
    def _entry(name: str, version: str, dep_type: str, source: str) -> dict[str, Any]:
        return {"name": name[:200], "version": version[:100] or "unknown", "type": dep_type, "sourceFile": source}

    def _parse_package_json(self, text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        try:
            data = json.loads(text)
        except ValueError:
            return [], source, ["npm"]
        entries: list[dict[str, Any]] = []
        for section, dep_type in (("dependencies", "runtime"), ("devDependencies", "dev"), ("peerDependencies", "peer"), ("optionalDependencies", "optional")):
            for name, version in (data.get(section) or {}).items():
                entries.append(self._entry(name, str(version), dep_type, source))
        return entries, source, ["npm"]

    @staticmethod
    def _parse_requirements(text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        entries: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("-r ", "--requirement ")):
                continue
            name = re.split(r"[=<>!~;\s]", line, maxsplit=1)[0]
            if not name or name.startswith("-"):
                continue
            version = _VERSION_RE.search(line)
            entries.append({"name": name[:200], "version": version.group(1) if version else "unknown", "type": "runtime", "sourceFile": source})
        return entries, source, ["pip"]

    @staticmethod
    def _parse_pyproject(text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        entries: list[dict[str, Any]] = []
        current_section: str | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                continue
            if current_section in {"dependencies", "project.dependencies", "project.optional-dependencies"}:
                cleaned = line.rstrip(",").strip()
                if cleaned.startswith('"') or cleaned.startswith("'"):
                    cleaned = cleaned.strip("\"'")
                name = re.split(r"[=<>~!;\s]", cleaned, maxsplit=1)[0]
                if name:
                    version = _VERSION_RE.search(cleaned)
                    entries.append({"name": name[:200], "version": version.group(1) if version else "unknown", "type": "runtime", "sourceFile": source})
        return entries, source, ["poetry", "uv", "pip"]

    @staticmethod
    def _parse_cargo(text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        entries: list[dict[str, Any]] = []
        in_deps = False
        in_dev = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                in_deps = line in {"[dependencies]", "[dev-dependencies]", "[build-dependencies]"}
                in_dev = line == "[dev-dependencies]"
                continue
            if in_deps and line and not line.startswith("#"):
                name = re.split(r"\s*=\s*", line, maxsplit=1)[0]
                if name:
                    version = _VERSION_RE.search(line)
                    entries.append({"name": name[:200], "version": version.group(1) if version else "unknown", "type": "dev" if in_dev else "runtime", "sourceFile": source})
        return entries, source, ["cargo"]

    @staticmethod
    def _parse_go_mod(text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        entries: list[dict[str, Any]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith(("require ", "require(")):
                continue
            if line.startswith(")"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(("github.com/", "golang.org/", "google.golang.org/", "gopkg.in/", "cloud.google.com/", "k8s.io/", "go.uber.org/")):
                entries.append({"name": parts[0][:200], "version": parts[1][:100], "type": "runtime", "sourceFile": source})
        return entries, source, ["go"]

    @staticmethod
    def _parse_generic(text: str, source: str) -> tuple[list[dict[str, Any]], str, list[str]]:
        entries: list[dict[str, Any]] = []
        if source.endswith("pom.xml"):
            for match in re.finditer(r"<artifactId>([^<]+)</artifactId>\s*<version>([^<]+)</version>", text):
                entries.append({"name": match.group(1)[:200], "version": match.group(2)[:100], "type": "runtime", "sourceFile": source})
            return entries, source, ["maven"]
        if source.endswith("Gemfile"):
            for match in re.finditer(r"^\s*gem\s+['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]+)['\"])?", text, re.MULTILINE):
                entries.append({"name": match.group(1)[:200], "version": match.group(2) or "unknown", "type": "runtime", "sourceFile": source})
            return entries, source, ["bundler"]
        for match in re.finditer(r"implementation\s+['\"]([^'\"]+):([^'\"]+)['\"]", text):
            entries.append({"name": match.group(1)[:200], "version": match.group(2)[:100], "type": "runtime", "sourceFile": source})
        return entries, source, ["gradle"]
