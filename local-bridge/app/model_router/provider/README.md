# Provider adapters

These adapters are deliberately metadata-only. They do not make network calls, read credentials, execute tools, modify files, or write Memory. Their responses contain an `agent_proposal` payload with `requiresApproval: true`; any future provider integration must preserve the existing Proposal → Approval → Execution boundary.
