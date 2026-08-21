# Model Router

The router is intentionally metadata-only in Phase 9. It classifies an
engineering task as `architecture`, `coding`, `debugging`, `testing`, or
`review`, then selects a registered model by capability. It never calls a
provider and never grants tool or execution permission.

Provider adapters may be added later behind `ModelProvider`; any provider
invocation must continue through the existing Preview → Approval → Execution
contract.
