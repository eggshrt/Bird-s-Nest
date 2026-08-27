---
name: skill-orchestrator
description: Explicit-only meta skill for turning a spoken request into a confirmed requirement contract, retrieving local Agent Skills, planning a dependency-aware DAG, executing after a second confirmation, and verifying results. Use only when the user explicitly invokes $skill-orchestrator.
---

# Skill Orchestrator

Orchestrate other skills without bypassing their instructions or the user's authority. Treat this file as the control protocol and each selected skill's `SKILL.md` as the task-specific protocol.

## Hard gates

Never execute task nodes until all gates before them are satisfied.

1. Confirm that the user explicitly invoked `$skill-orchestrator`. Otherwise explain how to invoke it and stop.
2. Load sibling `$grill-me` and follow it verbatim. Explore environment facts yourself. Close the design tree in rounds.
3. Present the shared understanding and obtain explicit confirmation.
4. Produce `RequirementContractV1`, retrieve skills, read candidate bodies, rerank, and produce `ExecutionPlanV1`.
5. Present the requirement contract, selected skills with evidence, permissions, side effects, risks, DAG, and verification methods. Obtain a second explicit confirmation.
6. Execute. The broad confirmation does not authorize publishing, payment, destructive work, credential changes, or a new external write. Request node-local confirmation immediately before any such action.

If any gate is incomplete, continue alignment or planning; do not call task-execution tools.

## Phase 1: Requirement alignment

Use `$grill-me` as the interview engine. Preserve its question format and frontier discipline. Do not invent a separate interview flow.

After the user confirms shared understanding, serialize the result as `RequirementContractV1` following [interfaces.md](references/interfaces.md). Include an English `retrieval_query` and compact English `retrieval_terms` even when the conversation is in another language. These are search fields, not a translation of the deliverable.

Write a redacted audit copy to `<project>/.codex/skill-orchestrator/runs/<run-id>/requirement.json`. Exclude secrets, tokens, credentials, unnecessary personal data, and large verbatim source content.

## Phase 2: Index and retrieve

On first use, run `scripts/bootstrap_runtime.py` without `--install`. Show the exact package versions, hashes, cache location, and network effect. Install only after the user confirms, using Codex-bundled Python 3.12 and `--install`. Never fall back to system Python 3.9.

Build or refresh the index with `scripts/orchestrator_index.py index`. Scan in this exact precedence:

1. project `.codex/skills`
2. project `.agents/skills`
3. user `.codex/skills`
4. user `.agents/skills`
5. plugin cache

The first definition wins; retain lower-priority same-name records as `shadowed`. Refresh only changed content hashes. Apply manual overrides from `.codex/skill-orchestrator/overrides.yaml` after derived fields.

Search with the normalized English retrieval query, not the user's last chat message. Request 12 lexical candidates. Apply permission, risk, input/output, and exclusion filters from the contract. Read the full `SKILL.md` for every surviving candidate and rerank with reasoning about fit. Return at most five candidates and mark the Top 3.

If confidence is low, names conflict, or a dangerous skill is selected, ask the user to review the relevant index fields before planning execution.

## Phase 3: Plan

Create `ExecutionPlanV1` following [interfaces.md](references/interfaces.md). Each node must have a stable id, exact skill name and source path, goal, input bindings, expected typed outputs, dependencies, execution mode, risk, side effects, required confirmations, and verification method.

Reject cycles, missing dependencies, invalid output bindings, and more than one allowed replan. Default all nodes to serial. Parallelize independent nodes only when the user explicitly authorizes subagents. A general instruction to execute is not subagent authorization.

Before the second confirmation, show:

- the normalized requirement contract and remaining assumptions;
- candidates, score evidence, exclusions, and selection rationale;
- permissions, external side effects, and risk per node;
- a readable DAG and node verification methods;
- exactly what the confirmation will and will not authorize.

Save a redacted plan audit copy beside `requirement.json`.

## Phase 4: Execute and verify

Load each selected skill body immediately before executing its node. Follow that skill faithfully. Pass only bound inputs. Keep artifacts and evidence associated with their node ids.

After every node, run its declared verification and record the observable evidence. Never mark a node successful based only on the absence of an error.

When verification fails:

1. record the error and evidence;
2. diagnose and replan only the affected downstream graph;
3. retry at most once across the whole run;
4. if verification still fails, stop and report the blocker without widening scope.

Produce `RunReportV1` and write a redacted copy to the run audit directory. The final user message must lead with the result, link artifacts, summarize validation evidence, identify any incomplete node, and state whether the one replan was used.

## GitHub fallback

Use GitHub fallback only when the local shortlist has no qualified candidate. Follow [github-fallback.md](references/github-fallback.md). Never install a candidate merely because it was found. Never run an unreviewed external script.

## Supporting references

- [interfaces.md](references/interfaces.md): stable interfaces and validation rules.
- [github-fallback.md](references/github-fallback.md): discovery, review, and pinned installation protocol.
- `scripts/orchestrator_index.py`: deterministic scan, enrichment, retrieval, plan validation, and external-skill audit.
- `scripts/bootstrap_runtime.py`: Python 3.12 and hash-locked runtime bootstrap.
