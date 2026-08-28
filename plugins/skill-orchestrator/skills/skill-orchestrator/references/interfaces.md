# Skill Orchestrator V2 interfaces

V2 is a breaking replacement. It does not import, migrate, or double-write `RequirementContractV1`, `ExecutionPlanV1`, or `RunReportV1`. Machine-readable schemas are in `references/schemas/v2/`.

## Contracts

- `RequirementContractV2`: goal, one authoritative asset input and hash, audience, target platform, scope, constraints, acceptance, canonical collaboration context, confirmations, and empty open questions.
- `CollaborationContextV1`: the four quadrants with provenance, confidence, impact, resolution status, and verification.
- `ExecutionGraphV2`: typed node definitions and a maximum of one automatic replan and three concurrent Agents.
- `AgentTaskV1`: run/node/task IDs, role, objective, context projection, dependency results, expected output, constraints, permissions, deadline, and dispatcher signature.
- `AgentResultV1`: status, summary, claims, evidence references, artifact paths/hashes, conflicts, at most three blocking questions per round, errors, and metrics. Large raw source bodies are not embedded.
- `DagPatchV1`: base graph version, explicit operations, exact invalidation set, semantic impact, evidence, and confirmation requirement.
- `RunEventV1`: immutable sequence, actor, graph version, correlation/causation IDs, redacted payload, and payload hash.
- `RunReportV2`: final status, node attempts, degradation/replan state, artifacts, validation, metrics, and conclusion.

## State

Run states are `draft`, `awaiting_initial_confirmation`, `running`, `awaiting_user`, `proposed`, `degraded_pending_acceptance`, `approved`, `failed`, and `canceled`.

Node states are `pending`, `ready`, `leased`, `running`, `awaiting_input`, `retry_scheduled`, `succeeded`, `failed`, `skipped`, `invalidated`, and `canceled`.

Only a final user confirmation changes a prompt package run from `proposed` to `approved`. A degraded run remains unapproved until the user explicitly accepts the degradation.

## Conflict authority

- Facts: original source evidence, then current validated breakdown, then sealed requirement summary, then Agent inference.
- Creative choices: latest sealed requirement and explicit user decisions, then Agent recommendation.
- Production: explicit production constraints, then validated production rules, then Agent preference.

Severe evidence conflicts and high-impact aesthetic conflicts pause for the user. The adjudicator provides one recommendation and the evidence that could change it; it does not count votes.

## Registered semantic types

The existing screenplay types remain registered: `screenplay_breakdown_v1`, `asset_catalog_v1`, `asset_context_snapshot_v1`, `visual_asset_requirement_v1`, and `creative_position_v1`.

V2 adds `requirement_contract_v2`, `collaboration_context_v1`, `execution_graph_v2`, `agent_task_v1`, `agent_result_v1`, `dag_patch_v1`, `run_event_v1`, and `run_report_v2`. v0.4 additionally registers `expert_position_v1`, `visual_prompt_spec_v1`, `reference_role_v1`, `prompt_salience_plan_v1`, `image_prompt_package_v2`, `derivative_request_v1`, and `external_capability_review_v1`.

`ImagePromptPackageV1` is read/export-only. New runs write `ImagePromptPackageV2`, which contains one asset, one confirmed spec hash, and one main prompt. It cannot contain a regenerated design statement, `negative_prompt`, model parameters, images, image-generation fields, or a second asset ID.
