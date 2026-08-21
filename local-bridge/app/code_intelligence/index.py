from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DependencyRecord, FileRecord, ScanSummary, SymbolRecord
from .parser import parse_source
from .scanner import CodeScanner
from .storage import CodeIndexStorage


class CodeIndex:
    def __init__(self, db_path: str | Path, scanner: CodeScanner | None = None) -> None:
        self.storage = CodeIndexStorage(db_path)
        self.scanner = scanner

    @property
    def db_path(self) -> Path:
        return self.storage.db_path

    def index_project(self, project: str) -> ScanSummary:
        if self.scanner is None:
            raise ValueError("CodeIndex requires a scanner to index a project")
        files = self.scanner.scan(project)
        conn = self.storage.connection
        conn.execute("DELETE FROM dependencies WHERE project=?", (project,))
        conn.execute("DELETE FROM symbols WHERE file_id IN (SELECT id FROM files WHERE project=?)", (project,))
        conn.execute("DELETE FROM files WHERE project=?", (project,))
        symbol_count = 0
        dependency_count = 0
        root = self.scanner.project_root(project)
        known_paths = {record.path for record in files}

        def resolve_dependency_target(source: str, target: str) -> str:
            """Resolve Python/relative module names to indexed project paths when possible."""
            normalized = target.strip()
            if normalized.startswith("."):
                parent = Path(source).parent
                normalized = (parent / normalized.lstrip(".").replace(".", "/")).as_posix()
            else:
                normalized = normalized.replace(".", "/")
            candidates = [normalized]
            if not Path(normalized).suffix:
                candidates.extend(f"{normalized}{suffix}" for suffix in (".py", ".ts", ".tsx", ".js", ".jsx"))
                candidates.append(f"{normalized}/__init__.py")
            return next((candidate for candidate in candidates if candidate in known_paths), target)

        for record in files:
            cursor = conn.execute("INSERT INTO files(project,path,language,hash,updated_at) VALUES(?,?,?,?,?)", (record.project, record.path, record.language, record.digest, record.updated_at))
            file_id = cursor.lastrowid
            symbols, dependencies = parse_source(root / record.path, record.path)
            for symbol in symbols:
                conn.execute("INSERT INTO symbols(file_id,type,name,signature,line_start,line_end) VALUES(?,?,?,?,?,?)", (file_id, symbol.symbol_type, symbol.name, symbol.signature, symbol.line_start, symbol.line_end))
            for dependency in dependencies:
                target = resolve_dependency_target(dependency.source, dependency.target)
                conn.execute("INSERT OR IGNORE INTO dependencies(project,source,target,type) VALUES(?,?,?,?)", (project, dependency.source, target, dependency.dependency_type))
            symbol_count += len(symbols)
            dependency_count += len(dependencies)
        conn.commit()
        return ScanSummary(project, len(files), symbol_count, dependency_count, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def files(self, project: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.storage.connection.execute("SELECT project,path,language,hash,updated_at FROM files WHERE project=? ORDER BY path LIMIT ?", (project, limit)).fetchall()
        return [{"project": row["project"], "path": row["path"], "language": row["language"], "hash": row["hash"], "updatedAt": row["updated_at"]} for row in rows]

    def search(self, project: str, query: str, limit: int = 100) -> list[dict[str, Any]]:
        term = f"%{query.strip()}%"
        rows = self.storage.connection.execute("""SELECT f.path,f.language,s.type,s.name,s.signature,s.line_start,s.line_end
            FROM symbols s JOIN files f ON f.id=s.file_id
            WHERE f.project=? AND (s.name LIKE ? OR s.signature LIKE ? OR f.path LIKE ?)
            ORDER BY s.name,f.path LIMIT ?""", (project, term, term, term, limit)).fetchall()
        return [{"path": row["path"], "language": row["language"], "type": row["type"], "name": row["name"], "signature": row["signature"], "lineStart": row["line_start"], "lineEnd": row["line_end"]} for row in rows]

    def symbol(self, project: str, name: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.search(project, name, limit)

    def dependencies(self, project: str, path: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if path:
            rows = self.storage.connection.execute("SELECT source,target,type FROM dependencies WHERE project=? AND (source=? OR target=?) ORDER BY source,target LIMIT ?", (project, path, path, limit)).fetchall()
        else:
            rows = self.storage.connection.execute("SELECT source,target,type FROM dependencies WHERE project=? ORDER BY source,target LIMIT ?", (project, limit)).fetchall()
        return [{"source": row["source"], "target": row["target"], "type": row["type"]} for row in rows]

    def stats(self, project: str) -> dict[str, int]:
        conn = self.storage.connection
        files = conn.execute("SELECT count(*) FROM files WHERE project=?", (project,)).fetchone()[0]
        symbols = conn.execute("SELECT count(*) FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.project=?", (project,)).fetchone()[0]
        dependencies = conn.execute("SELECT count(*) FROM dependencies WHERE project=?", (project,)).fetchone()[0]
        return {"files": files, "symbols": symbols, "dependencies": dependencies}
