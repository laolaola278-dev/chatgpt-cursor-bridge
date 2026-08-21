Phase 18 security regressions live in `local-bridge/tests/security/` and run with:

```sh
cd local-bridge && pytest -q tests/security
```

These tests assert that unsafe behavior remains unavailable; they do not perform deployment or external provider calls.
