"""Git diff formatting and output limits."""

from __future__ import annotations

MAX_GIT_OUTPUT_BYTES = 512 * 1024


def limit_git_output(raw: bytes, limit: int = MAX_GIT_OUTPUT_BYTES) -> tuple[str, bool]:
    if len(raw) <= limit:
        return raw.decode("utf-8", errors="replace"), False
    marker = b"\n... [git output truncated]\n"
    return (raw[: limit - len(marker)] + marker).decode("utf-8", errors="replace"), True
