from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import Settings
from app.security.sandbox import get_project_dir

from .models import FileRecord
from .parser import EXTENSIONS, language_for


class CodeScanner:
    """Enumerate source files and hashes without changing project files."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def project_root(self, project: str) -> Path:
        return get_project_dir(project, self.settings)

    def files(self, project: str) -> Iterable[tuple[Path, str]]:
        root = self.project_root(project)
        ignored = set(self.settings.ignored_names) | {".git", "node_modules", "__pycache__"}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            relative = path.relative_to(root)
            if any(part in ignored or part.startswith(".") for part in relative.parts[:-1]):
                continue
            yield path, relative.as_posix()

    def scan(self, project: str) -> list[FileRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records: list[FileRecord] = []
        for path, relative in self.files(project):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(FileRecord(project, relative, language_for(path), digest, now))
        return records
