"""Phase 30 · Deterministic context deduplication.

Duplicate content (same file, same symbol, same snippet) is collapsed by a
stable content hash plus a symbol/path identity. Duplicates are dropped and
counted so the UI can report how many candidates were collapsed. Everything
is deterministic and scoped to one project.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from .models import ContextCandidate, DedupReport


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def candidate_identity(candidate: ContextCandidate) -> str:
    """Identity used to collapse repeated symbols / files / snippets."""
    if candidate.kind == "symbol":
        return f"symbol:{candidate.path}:{candidate.name}"
    return f"{candidate.kind}:{candidate.path}:{content_hash(candidate.content)[:12]}"


class ContextDeduplicator:
    def deduplicate(self, candidates: Iterable[ContextCandidate]) -> tuple[list[ContextCandidate], DedupReport]:
        seen_hashes: set[str] = set()
        seen_identities: set[str] = set()
        unique: list[ContextCandidate] = []
        dropped = 0
        total = 0
        for candidate in candidates:
            total += 1
            digest = content_hash(candidate.content)
            identity = candidate_identity(candidate)
            if digest in seen_hashes or identity in seen_identities:
                dropped += 1
                continue
            seen_hashes.add(digest)
            seen_identities.add(identity)
            unique.append(candidate)
        return unique, DedupReport(total_candidates=total, unique=len(unique), dropped=dropped)
