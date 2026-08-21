from __future__ import annotations

from .index import CodeIndex


def reverse_impact(index: CodeIndex, project: str, changed_paths: list[str], limit: int = 200) -> list[str]:
    edges = index.dependencies(project, limit=2000)
    reverse: dict[str, set[str]] = {}
    for edge in edges:
        reverse.setdefault(edge["target"], set()).add(edge["source"])
    seen: set[str] = set(changed_paths)
    queue = list(changed_paths)
    while queue and len(seen) < limit:
        current = queue.pop(0)
        for dependent in sorted(reverse.get(current, set())):
            if dependent not in seen:
                seen.add(dependent)
                queue.append(dependent)
    return sorted(seen - set(changed_paths))
