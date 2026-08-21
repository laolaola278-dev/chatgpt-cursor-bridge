# Phase 25 · Engineering Intelligence Evolution

## Status

Phase 25 adds a deterministic, project-scoped Engineering Intelligence Layer on top of the Phase 24 strategy and decision system.

```text
Engineering Events
        ↓
Observation
        ↓
Pattern Detection
        ↓
Risk Prediction
        ↓
Recommendation
        ↓
Human Decision
        ↓
Controlled Action (existing approval chain)
        ↓
Outcome
        ↓
Evidence
        ↓
Knowledge Evolution (approval-gated proposal)
```

The intelligence layer observes and analyzes engineering metadata. It is not an autonomous executor, repairer, approver, or source editor.

## Architecture

### Observation Model

`app/intelligence/observation/` defines the unified `Observation` model and SQLite `ObservationStore`.

Supported event types:

- `code_change`
- `test_result`
- `build_result`
- `git_diff`
- `dependency_change`
- `error_event`
- `performance_event`
- `architecture_event`

Every record carries `id`, `project_id`, `timestamp`, `type`, `source`, `summary`, `metadata`, and `risk_level`. The store is indexed by project and timestamp and maintains an observation audit table. Metadata, text, sources, and evidence references are bounded and secret-scrubbed before persistence.

Observation recording through the HTTP API is a Level 1 ApprovalStore request. Direct analysis does not read or modify project source files.

### Pattern Intelligence

`app/intelligence/pattern_intelligence/` provides read-only, deterministic detectors for:

- historical similarity
- repeated failures
- repeated changes
- regression patterns
- dependency patterns
- performance degradation

`PatternResult` contains a generated pattern id, project id, pattern type, observation-backed evidence, similar historical observations, confidence, and summary. Pattern persistence is performed only by the approval execution path for an explicitly approved analysis request.

### Risk Prediction and Recommendation

`app/intelligence/risk_prediction/` maps evidence-backed patterns to bounded `PredictionResult` records for regression, build, test, dependency, architecture, and performance risk. Confidence is explicit and capped below certainty; predictions always expose the observation/pattern evidence ids that produced them.

The Phase 25 projection in `app/intelligence/recommendation.py` turns predictions into `IntelligenceRecommendation` records. Recommendations contain rationale, evidence, confidence, and risk, but no executable operation, command, patch, or permission.

### Strategy Outcome Tracking

`app/intelligence/outcome.py` adds `StrategyOutcome` and `OutcomeStore`. A record links a strategy and optional decision to `SUCCESS`, `PARTIAL_SUCCESS`, `FAILURE`, or `CANCELLED`, and captures:

- expected outcome
- actual outcome
- difference
- evidence
- source (`test_result`, `build_result`, `user_decision`, or another audited event)
- confidence

The `/intelligence/outcomes/record` route queues the record in ApprovalStore; the strategy system itself is never executed by this layer.

### Decision Evidence 2.0

`app/intelligence/evidence/` provides `EvidenceBundle`, `EvidenceStore`, and `DecisionEvidenceManager`. A bundle can associate observations, patterns, predictions, risks, strategies, recommendations, historical evidence, provenance, and a decision id. Bundles are project-scoped and can be inspected through a read-only API. Creation and linking are metadata writes that remain approval-gated.

### Intelligence Memory

`app/memory/intelligence/` stores four knowledge categories:

- `patterns`
- `predictions`
- `strategies`
- `outcomes`

`IntelligenceMemory.preview()` has no filesystem side effect. `append_after_approval()` is called only from the central approved-action dispatcher and writes project-isolated JSONL records with source, evidence, confidence, timestamp, and scrubbed metadata. Observation, pattern, or prediction analysis never calls the memory writer automatically.

### Quality Gate 11

`app/quality/gate11.py` implements `QualityGate11Evaluator`. It reports `PASS`, `WARN`, or `BLOCK` and checks:

- observation integrity
- pattern evidence
- prediction confidence
- recommendation traceability
- decision evidence
- outcome completeness
- knowledge provenance

The gate is read-only. It reports blockers and warnings but does not repair data, stop execution, approve a request, or modify source.

## API

All Phase 25 GET endpoints require a project identifier, return `readOnly: true`, and filter data by that project:

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/intelligence/observations?project={project}` | Observation timeline |
| GET | `/intelligence/patterns?project={project}` | Stored or on-demand patterns |
| GET | `/intelligence/predictions?project={project}` | Stored or on-demand predictions |
| GET | `/intelligence/recommendations?project={project}` | Evidence-backed recommendations |
| GET | `/intelligence/decisions?project={project}` | Existing project-scoped decisions |
| GET | `/intelligence/outcomes?project={project}` | Strategy outcomes |
| GET | `/intelligence/knowledge?project={project}` | Approved intelligence knowledge |
| GET | `/intelligence/evidence?project={project}` | Evidence bundles |
| GET | `/intelligence/evidence/{bundle_id}?project={project}` | One project-scoped bundle |
| GET | `/intelligence/decisions/{decision_id}/evidence?project={project}` | Decision evidence lookup |
| GET | `/intelligence/quality?project={project}` | Quality Gate 11 report |
| GET | `/quality/v11/{project}` | Versioned Quality Gate 11 report |

Persistent Phase 25 POST endpoints do not write immediately:

- `POST /intelligence/observations/record`
- `POST /intelligence/patterns/analyze`
- `POST /intelligence/predictions/analyze`
- `POST /intelligence/outcomes/record`
- `POST /intelligence/knowledge/propose`
- `POST /intelligence/evidence/bundle`

Each returns a pending approval request and uses the existing:

```text
Proposal → Risk Evaluation → Approval Queue → Human Approval
         → Controlled metadata write → Audit
```

No endpoint calls a shell, an external model, a source editor, or an action executor from the intelligence implementation.

## Read-only Dashboard

The extension updates `src/intelligence/` and the existing panel to display:

- observation timeline
- pattern and prediction counts
- confidence and risk
- recommendations
- decisions
- strategy outcomes
- evidence bundle counts
- approved knowledge records
- Quality Gate 11 state

The dashboard is text-only for Phase 25. It renders no `Execute`, `Approve`, `Fix`, `Apply`, `Auto Fix`, or `Auto Approve` controls and does not create a new execution path.

## Security Boundary

Phase 25 explicitly does not implement:

- automatic execution
- automatic approval
- automatic repair
- source modification
- shell or arbitrary command execution
- external LLM/API calls
- agent privilege escalation
- automatic Memory writes
- Git commits
- ApprovalStore bypasses

Security controls include project-scoped queries, SQLite project indexes, explicit evidence provenance, bounded confidence, recursive secret/path scrubbing, audit records for observation writes and reads, and a central approved-action dispatch path for all persistent Phase 25 writes.

## Testing

Phase 25 verification added:

- `tests/test_phase25_observation.py`
- `tests/test_phase25_pattern_intelligence.py`
- `tests/test_phase25_prediction.py`
- `tests/test_phase25_strategy_outcome.py`
- `tests/test_phase25_decision_evidence.py`
- `tests/test_phase25_intelligence_memory.py`
- `tests/test_phase25_quality.py`
- `tests/test_phase25_api.py`
- `tests/security/test_phase25_intelligence_security.py`
- `browser-extension/tests/intelligence-evolution.test.ts`

Latest targeted verification:

- Backend Phase 25 tests: **32 passed**
- Extension test suite: **1114 passed**
- Extension TypeScript typecheck: **0 errors**
- Python `compileall`: passed
- `git diff --check`: passed

The complete backend regression suite was run in stable groups because the monolithic invocation exceeded the sandbox command window: **45 test files / 1833 collected tests passed** across the full suite. Phase 25 does not claim autonomous engineering; it provides observe/analyze/predict/recommend/learn metadata under human supervision.
