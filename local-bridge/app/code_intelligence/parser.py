from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import DependencyRecord, SymbolRecord


EXTENSIONS = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".cpp": "C++", ".h": "C++", ".hpp": "C++"}


def language_for(path: Path) -> str:
    return EXTENSIONS.get(path.suffix.lower(), "Unknown")


def _line_end(lines: list[str], start: int) -> int:
    if not lines:
        return start
    return min(len(lines), start + 1)


def parse_source(path: Path, relative_path: str) -> tuple[list[SymbolRecord], list[DependencyRecord]]:
    """Parse declarations/imports only; never imports or executes project code."""
    language = language_for(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    lines = text.splitlines()
    symbols: list[SymbolRecord] = []
    dependencies: list[DependencyRecord] = []

    if language == "Python":
        try:
            tree = ast.parse(text, filename=relative_path)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = ast.unparse(node.args) if hasattr(ast, "unparse") else "..."
                    symbols.append(SymbolRecord(relative_path, "function", node.name, f"{node.name}({args})", node.lineno, getattr(node, "end_lineno", node.lineno)))
                elif isinstance(node, ast.ClassDef):
                    symbols.append(SymbolRecord(relative_path, "class", node.name, f"class {node.name}", node.lineno, getattr(node, "end_lineno", node.lineno)))
                elif isinstance(node, ast.Import):
                    for item in node.names:
                        dependencies.append(DependencyRecord(relative_path, item.name, "import"))
                elif isinstance(node, ast.ImportFrom):
                    module = "." * node.level + (node.module or "")
                    dependencies.append(DependencyRecord(relative_path, module, "from_import"))
        return symbols, dependencies

    patterns = [
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*(\([^\n]*\))?")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^\n]*\)\s*=>")),
        ("function", re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*(\([^\n]*\))?")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*=")),
        ("enum", re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+([A-Za-z_$][\w$]*)")),
        ("variable", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?!\s*\(|\s*async\s*\()")),
    ]
    import_pattern = re.compile(r"^\s*(?:import\s+(?:.+?\s+from\s+)?|from\s+)([\"'])(.+?)\1")
    for number, line in enumerate(lines, start=1):
        for symbol_type, pattern in patterns:
            match = pattern.search(line)
            if match:
                name = match.group(1)
                symbols.append(SymbolRecord(relative_path, symbol_type, name, line.strip()[:500], number, _line_end(lines, number)))
                break
        match = import_pattern.search(line)
        if match:
            dependencies.append(DependencyRecord(relative_path, match.group(2), "import"))
    return symbols, dependencies
