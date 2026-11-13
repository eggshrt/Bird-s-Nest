# v0.4 workflow

```text
sealed requirement + confirmed presentation
                 │
        evidence guardian
                 │
    asset specialist + six independent positions
                 │
        visual spec assembler
             ┌───┴───┐
   production review  adversarial review
             └───┬───┘
        evidence adjudication
                 │
        gate 2: spec confirmation
                 │
        salience editor → OpenAI compiler
                 │
        gate 3: final confirmation → files
```

All six creative roles execute on every run. The matching asset specialist also executes; `reference-role-director` runs only when the user supplied references. Conflicts are resolved by evidence authority, not voting. A real conflict may trigger at most one targeted rebuttal round, recorded in the spec.

`preview`, `run`, `confirm-spec`, `approve`, and `resume` all call the same upstream `validate_handoff` function. Validation checks the current requirement, companion catalog, snapshot and creative position, content-bound confirmations, and source/baseline freshness on disk. Later gates also retain the run's original requirement-file hash check. A changed source or companion file blocks continuation even when the requirement file itself is unchanged; no confirmation or answer event is recorded until revalidation succeeds. Return to concept direction to refresh and reconfirm the affected contract before starting a new run.

Idempotent nodes retry once. Each run allows one automatic affected-subgraph replan. App Server or scheduler interruption resumes from events and thread IDs. A pre-v0.4 run is read/export-only. Full execution mode is required; degraded output cannot be silently promoted.

Changed wording, framing, or adapter behavior may invalidate only downstream nodes if all invariants remain visible. Changed asset identity, design direction, or core acceptance freezes the run and returns to concept direction.

## Canonical input and role projection

The upstream now publishes one Chinese concept-design book while preserving its sealed six-file machine package under the internal working root. Take `machine_handoff` from the concept materializer's `--details` result when coordinating automatically; do not ask the user to manage or upload backend files already available locally. The readable book is linked for the user, never regenerated here. Existing legacy package locations remain valid.

Validate the complete original package before constructing role inputs. Use the runtime's labeled `RoleRequirementViewV1` for creative roles and the full requirement for review roles. Remove only confirmation, persistence-plan, and integrity bookkeeping; retain all creative content, evidence, source provenance, references, constraints, overrides, and acceptance criteria. `CollaborationContextViewV1.shared_known_ref` points to the complete inline `requirement.evidence` only for an exact generated duplicate; preserve independent context. `AgentResultViewV1` removes only redundant result bookkeeping, retaining substantive findings and conflicts. Projection saves repeated context; it does not create a weaker handoff contract or authorize redesign. Update canonical data by deltas and regenerate projections mechanically; do not rewrite whole requirements into role-specific prose.

Keep scratch work and role intermediate artifacts under `work/`. Existing event storage remains internal; JSONL/SQLite is not a new user deliverable, and gzip/base64 is not a model-token optimization.
