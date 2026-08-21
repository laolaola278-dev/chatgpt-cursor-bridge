"""Phase 30 · Prompt Injection Protection.

Project files and user-supplied content are classified as UNTRUSTED. This
module detects classic injection phrases and always keeps a strict separation
between system instruction, user instruction, project content, tool output and
external content. Detected signals never become instructions — they are
reported as data so the UI can warn the user.
"""

from __future__ import annotations

from .models import InjectionReport, InjectionSignal

# (pattern, severity, label)
_SIGNATURES: list[tuple[str, str, str]] = [
    ("ignore previous instructions", "high", "instruction override"),
    ("ignore all previous", "high", "instruction override"),
    ("disregard previous", "high", "instruction override"),
    ("system prompt", "warning", "system-prompt reference"),
    ("you are now", "warning", "role takeover"),
    ("act as", "info", "role instruction in content"),
    ("run this command", "high", "command instruction"),
    ("execute the command", "high", "command instruction"),
    ("run the following command", "high", "command instruction"),
    ("send secrets", "high", "secret exfiltration request"),
    ("exfiltrate", "high", "secret exfiltration request"),
    ("reveal your api key", "high", "secret exfiltration request"),
    ("approve this operation", "warning", "approval bypass request"),
    ("approve automatically", "high", "approval bypass request"),
    ("auto approve", "high", "approval bypass request"),
    ("do not ask for approval", "high", "approval bypass request"),
    ("bypass approval", "high", "approval bypass request"),
    ("modify the file", "info", "mutation instruction"),
    ("write to disk", "info", "mutation instruction"),
]

#: Sources that are never trusted as instructions when they come from project
#: files, tool output or the page DOM.
UNTRUSTED_SOURCES = ("project_content", "tool_output", "external_content", "page_dom")


class PromptInjectionGuard:
    def detect(self, text: str, *, source: str = "project_content") -> InjectionReport:
        lowered = (text or "").lower()
        signals: list[InjectionSignal] = []
        for phrase, severity, label in _SIGNATURES:
            index = lowered.find(phrase)
            if index >= 0:
                snippet = (text[max(0, index - 20) : index + len(phrase) + 20]).replace("\n", " ")[:80]
                signals.append(InjectionSignal(pattern=label, severity=severity, snippet=snippet))
        verdict = "clean"
        if any(signal.severity == "high" for signal in signals):
            verdict = "untrusted_content_detected"
        elif signals:
            verdict = "suspicious"
        return InjectionReport(
            project="",
            trusted="system",
            untrusted=[source] if source in UNTRUSTED_SOURCES else ["project_content"],
            signals=signals,
            verdict=verdict,
        )
