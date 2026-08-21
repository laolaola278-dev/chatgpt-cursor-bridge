from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterResponse:
    provider: str
    model: str
    operation: str
    content: str = ""
    status: str = "adapter_only"
    requires_approval: bool = True
    proposal: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "operation": self.operation, "content": self.content, "status": self.status, "requiresApproval": self.requires_approval, "proposal": self.proposal, "readOnly": True}


class ModelProvider(Protocol):
    name: str
    def chat(self, prompt: str, *, model: str) -> AdapterResponse: ...
    def analyze(self, prompt: str, *, model: str) -> AdapterResponse: ...
    def review(self, prompt: str, *, model: str) -> AdapterResponse: ...


def metadata_response(provider: str, model: str, operation: str, prompt: str) -> AdapterResponse:
    return AdapterResponse(provider, model, operation, content="", proposal={"type": "agent_proposal", "prompt": prompt, "operations": [], "execution": "approval_required"})
