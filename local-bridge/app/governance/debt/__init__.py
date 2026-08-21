"""Technical debt management.

Debt items follow a strict forward lifecycle (OPEN -> ANALYZING -> PROPOSED ->
APPROVED -> RESOLVED -> VERIFIED). Every mutation is approval-gated at the API
layer; the manager itself only records approved transitions.
"""

from .manager import DebtManager

__all__ = ["DebtManager"]
