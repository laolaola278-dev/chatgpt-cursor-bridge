"""Phase 33 · Optional real-provider validation (spec §11–§13).

**This package is skipped by default.** Nothing inside it runs unless a real
credential *and* an explicit opt-in are both present in the environment:

```bash
OPENAI_API_KEY=<your key> REAL_LLM_RUN=1 python -m pytest tests/real -q
```

Missing either one skips every test, so a normal ``pytest -q`` never spends a
token, never opens an outbound connection and never needs a credential.

Safety rules that apply to every module here (§13):

* the key, the ``Authorization`` header, any Bearer token and any raw provider
  response body are **never** printed, asserted on verbatim, written to a
  fixture, a snapshot, a log or a report — not even in a failure message;
* nothing here bypasses the ApprovalStore or writes to the repository;
* no request is made purely to provoke a provider into rate-limiting us.
"""

from __future__ import annotations

import os

# Both gates must be set. ``REAL_LLM_RUN`` is the explicit human opt-in; the key
# alone (which a developer may well have exported for unrelated work) is not
# enough to start spending real tokens.
REAL_RUN_FLAG = "REAL_LLM_RUN"
KEY_ENV = "OPENAI_API_KEY"


def real_run_enabled() -> bool:
    return bool(os.environ.get(KEY_ENV, "").strip()) and os.environ.get(REAL_RUN_FLAG) == "1"


def skip_reason() -> str:
    return (
        f"real provider tests are opt-in: set {KEY_ENV}=<real key> and "
        f"{REAL_RUN_FLAG}=1 to enable them"
    )


__all__ = ["KEY_ENV", "REAL_RUN_FLAG", "real_run_enabled", "skip_reason"]
