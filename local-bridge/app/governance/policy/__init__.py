"""Engineering policy engine.

Policies translate governance signals into pass / warning / approval_required
outcomes only. They can never block or trigger execution themselves; the
execution chain always remains Proposal -> Risk -> Approval -> Human Approval.
"""

from .engine import PolicyEngine

__all__ = ["PolicyEngine"]
