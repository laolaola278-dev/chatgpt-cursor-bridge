from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FileRecord:
    project: str
    path: str
    language: str
    digest: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {"project": self.project, "path": self.path, "language": self.language, "hash": self.digest, "updatedAt": self.updated_at}


@dataclass(frozen=True)
class SymbolRecord:
    path: str
    symbol_type: str
    name: str
    signature: str
    line_start: int
    line_end: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "type": self.symbol_type, "name": self.name, "signature": self.signature, "lineStart": self.line_start, "lineEnd": self.line_end}


@dataclass(frozen=True)
class DependencyRecord:
    source: str
    target: str
    dependency_type: str

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "type": self.dependency_type}


@dataclass(frozen=True)
class ScanSummary:
    project: str
    files: int
    symbols: int
    dependencies: int
    indexed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {"project": self.project, "files": self.files, "symbols": self.symbols, "dependencies": self.dependencies, "indexedAt": self.indexed_at}
