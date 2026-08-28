---
name: skill-orchestrator
description: Explicit-only V2 controller for aligning a requirement, retrieving local Skills, proposing a typed DAG, and driving a recoverable Codex multi-Agent run with event-sourced audit and evidence-backed validation. Use only when the user explicitly invokes $skill-orchestrator.
metadata:
  input_types: [spoken_requirement, visual_asset_requirement_v1]
  output_types: [requirement_contract_v2, execution_graph_v2, run_report_v2]
---

# Skill Orchestrator V2

This Skill is the semantic controller. It defines goals and typed tasks; `scripts/orchestrator_runtime.py` is the deterministic scheduler. Never let an LLM mutate scheduler state or silently repair a DAG.

## Hard gates

1. Require explicit `$skill-orchestrator` invocation.
2. Load sibling `$grill-me`, inspect discoverable facts, close the design tree, and confirm shared understanding.
3. Create `RequirementContractV2` and one versioned `CollaborationContextV1`.
4. Refresh the local Skill index, retrieve against the normalized contract, read qualified Skill bodies, and propose `ExecutionGraphV2`.
5. Show goal, selected Skills, evidence, Agent count, peak concurrency, permissions, side effects, DAG, and verification. Obtain execution confirmation.
6. Only then create a run in the V2 event store and execute it.

Danger mode is a host prerequisite, not business authorization. Never modify Codex configuration. Publishing, payment, destructive work, credentials, image generation, and new external writes still need explicit node-local authorization; the v0.4 runtime rejects these side effects by default.

## Four-quadrant context

Maintain one canonical collaboration context with `shared_known`, `user_context_gaps`, `agent_added_context`, and `joint_unknown_hypotheses`. Every entry records provenance, confidence, impact, status, and verification. Agents receive task-bounded projections and return discoveries as `AgentResultV1`; they do not interview the user. Deduplicate blocking questions and ask at most three per round, with no round limit.

## Retrieval

Run the hash-locked bootstrap only with Codex-bundled Python 3.12+. Preserve scan precedence:

1. project `.codex/skills`
2. project `.agents/skills`
3. user `.codex/skills`
4. user `.agents/skills`
5. plugin cache

The first same-name definition wins and lower-priority copies remain `shadowed`. Retrieve up to 12 lexical candidates, apply input/output, risk, permission, and exclusion filters, then read candidate bodies and rerank to at most five with a Top 3. Dynamic experts require local presence, at least 0.8 confidence, compatible input, and no network/external-write permission; choose at most two and choose none when no candidate qualifies.

Use [github-fallback.md](references/github-fallback.md) only when local retrieval has no qualified candidate. Never auto-install or run an unreviewed external script.

## DAG and scheduling

Every node declares a unique ID, role Skill, objective, input bindings, output schema, dependencies, execution mode, idempotency, soft/hard timeout, permissions, side effects, risk, and verification.

- Reject cycles, missing bindings, duplicate objectives, forbidden effects, and concurrency above three.
- The scheduler may detect a problem but never silently change task semantics. The controller proposes `DagPatchV1`; high-impact patches need reconfirmation.
- A goal-preserving addition may update the current graph. A changed goal, asset, requirement hash, or core acceptance criterion freezes the run and derives a new one.
- Changed upstream inputs invalidate every affected descendant.
- Idempotent nodes retry once. Non-idempotent nodes do not auto-retry. One automatic affected-subgraph replan is allowed per run.
- Read-only work may fall back to single-Agent serial execution only as `degraded`, requiring explicit acceptance.

Use the adaptive cap `min(3, host slots, ready nodes, actual experts)`. Keep shared project facts read-only and give every node a private writable directory with declared artifact bindings.

## State and recovery

The project SQLite database uses an append-only `RunEventV1` log as truth. Run/node/approval/artifact/metric tables are disposable projections. Use `run`, `resume`, `status`, `cancel`, `export`, `prune`, and `replay`; cancellation is cooperative for 30 seconds before forced interruption. Default node soft/hard timeouts are 300/600 seconds, with a 20-second heartbeat and 60-second lease.

The Codex App Server bridge starts, resumes, interrupts, and archives Agent threads. Persist thread IDs. Promise process-level local recovery only, never cluster HA.

## Bundled verticals

- `$ai-script-breakdown` produces `screenplay_breakdown_v1`.
- `$screenplay-concept-director` consumes the baseline and produces a sealed `visual_asset_requirement_v1` without prompt fields.
- `$image-prompt-team` exclusively consumes that sealed requirement, pauses for `visual_prompt_spec_v1` confirmation, and then produces `image_prompt_package_v2` plus `run_report_v2`.

The specialized domain validators remain authoritative. The generic controller must not weaken their evidence, freshness, single-asset, confirmation, or no-image boundaries.

## References and scripts

- [interfaces.md](references/interfaces.md): V2 contracts, states, patch rules, and semantic registrations.
- [github-fallback.md](references/github-fallback.md): reviewed, pinned GitHub candidate flow.
- `scripts/orchestrator_index.py`: index, retrieval, V2 graph validation, and external Skill audit.
- `scripts/orchestrator_runtime.py`: event store, scheduler, App Server bridge, recovery, export, and pruning.
- `scripts/bootstrap_runtime.py`: Python 3.12 hash-locked dependency bootstrap.
