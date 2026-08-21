from __future__ import annotations

REFERENCE_CASES: dict[str, dict] = {
    "bug_fix": {
        "name": "Bug Fix",
        "stages": ["ISSUE", "CONTEXT_ANALYSIS", "AGENT_PLANNING", "PROPOSAL", "APPROVAL", "EXECUTION", "VERIFICATION"],
    },
    "refactoring": {
        "name": "Refactoring",
        "stages": ["CODE_INTELLIGENCE", "IMPACT_ANALYSIS", "SIMULATION", "DECISION", "PLAN", "EXECUTION"],
    },
    "failure_recovery": {
        "name": "Failure Recovery",
        "stages": ["EXECUTION_FAILURE", "ROLLBACK", "FAILURE_INTELLIGENCE", "LEARNING_MEMORY"],
    },
}


def reference_case(case_id: str) -> dict | None:
    return REFERENCE_CASES.get(case_id)
