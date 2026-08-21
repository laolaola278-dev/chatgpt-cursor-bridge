"""Minimal, strict unified-diff patch engine.

Only single-file, in-place patches are supported. Whole project overwrites and
file creation through patches are intentionally rejected in Phase 1.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.security.sandbox import validate_path
from app.security.validator import ValidationFailed, ensure_patch, ensure_text_payload, read_text_file
from app.workspace.file_service import build_preview, unified_diff

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
SKIPPED_PREFIXES = ("--- ", "+++ ", "diff ", "index ", "new file mode", "deleted file mode")


def apply_unified_diff(original: str, patch: str) -> str:
    """Apply ``patch`` to ``original`` with strict context verification."""
    original_lines = original.splitlines()
    patch_lines = patch.splitlines()

    result: list[str] = []
    cursor = 0
    index = 0
    hunks = 0

    while index < len(patch_lines):
        line = patch_lines[index]

        if not line.strip() or line.startswith(SKIPPED_PREFIXES):
            index += 1
            continue

        header = HUNK_HEADER.match(line)
        if not header:
            raise ValidationFailed(f"Unexpected line outside of a hunk: {line[:80]!r}")

        start = max(int(header.group(1)) - 1, 0)
        if start < cursor:
            raise ValidationFailed("Patch hunks must be ordered and must not overlap")
        if start > len(original_lines):
            raise ValidationFailed("Patch hunk starts beyond the end of the file")

        result.extend(original_lines[cursor:start])
        cursor = start
        index += 1

        while index < len(patch_lines) and not HUNK_HEADER.match(patch_lines[index]):
            hunk_line = patch_lines[index]
            if hunk_line.startswith("\\"):  # "\ No newline at end of file"
                index += 1
                continue
            if hunk_line.startswith(SKIPPED_PREFIXES):
                break

            tag = hunk_line[:1]
            text = hunk_line[1:]

            if tag in {" ", ""}:
                if cursor >= len(original_lines) or original_lines[cursor] != text:
                    raise ValidationFailed(
                        f"Context mismatch at line {cursor + 1}; the file changed since the diff was generated"
                    )
                result.append(original_lines[cursor])
                cursor += 1
            elif tag == "-":
                if cursor >= len(original_lines) or original_lines[cursor] != text:
                    raise ValidationFailed(
                        f"Removal mismatch at line {cursor + 1}; the file changed since the diff was generated"
                    )
                cursor += 1
            elif tag == "+":
                result.append(text)
            else:
                raise ValidationFailed(f"Invalid patch line prefix: {hunk_line[:1]!r}")

            index += 1

        hunks += 1

    if hunks == 0:
        raise ValidationFailed("Patch does not contain any hunk")

    result.extend(original_lines[cursor:])
    patched = "\n".join(result)
    if patched and original.endswith("\n"):
        patched += "\n"
    if patched and not original:
        patched += "\n"
    return patched


class PatchService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _load(self, project: str, path: str) -> tuple[str, Any]:
        target = validate_path(project, path, self._settings, must_exist=True)
        content, _ = read_text_file(target, self._settings)
        return content, target

    def preview(self, project: str, path: str, patch: str) -> str:
        cleaned = ensure_patch(patch)
        original, _ = self._load(project, path)
        patched = apply_unified_diff(original, cleaned)
        ensure_text_payload(patched, self._settings)
        return build_preview(unified_diff(original, patched, path) or "(no textual changes)")

    def apply(self, project: str, path: str, patch: str) -> dict[str, Any]:
        cleaned = ensure_patch(patch)
        original, target = self._load(project, path)
        patched = apply_unified_diff(original, cleaned)
        encoded = ensure_text_payload(patched, self._settings)
        diff = unified_diff(original, patched, path)
        target.write_bytes(encoded)
        return {
            "file": path,
            "size": len(encoded),
            "hunksApplied": len(HUNK_HEADER.findall(cleaned)) or cleaned.count("@@ -"),
            "diff": build_preview(diff),
        }
