"""Test execution limits."""

from __future__ import annotations

DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 600


def clamp_timeout(value: int, configured: int = DEFAULT_TIMEOUT_SECONDS) -> int:
    if value <= 0:
        return configured
    return max(MIN_TIMEOUT_SECONDS, min(value, MAX_TIMEOUT_SECONDS, configured))


def truncate_output(value: bytes, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value.decode("utf-8", errors="replace"), False
    marker = b"\n... [output truncated by ChatGPT Cursor Bridge]\n"
    available = max(0, limit - len(marker))
    return (value[:available] + marker).decode("utf-8", errors="replace"), True
