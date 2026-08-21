"""Governance timeline memory.

Stores health reports, drift reports, debt history and policy events under
memory/governance/. Writes are only performed through append_after_approval,
which the API layer invokes after a separate human approval of a memory
proposal.
"""

from .project_memory import GovernanceMemory

__all__ = ["GovernanceMemory"]
