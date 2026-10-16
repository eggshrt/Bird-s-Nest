# v0.4 interfaces

Public flow:

- Input: one sealed `VisualAssetRequirementV1`.
- Expert output: `ExpertPositionV1`.
- Intermediate contract: `VisualPromptSpecV1`.
- Optional user-reference contract: `ReferenceRoleV1`.
- Final output: `ImagePromptPackageV2` plus `RunReportV2`.
- Deferred work request: `DerivativeRequestV1`.
- External Skill candidate audit: `ExternalCapabilityReviewV1`.

`ImagePromptPackageV1` remains read/export-only. v0.4 runs never import, resume, or dual-write it. The SQLite event schema remains V2 so existing audit databases can still be inspected.

`visual_prompt_spec_hash` identifies creative spec content and excludes mutable approval fields (`status` and `spec_confirmation`). This lets the second-gate timestamp be recorded without changing the compiled content identity.

Formal output:

```text
outputs/image-prompt-team/<project>/<draft>/assets/<asset-id>/<version>/
├── generation-prompt.txt
├── visual-prompt-spec.json
├── prompt-package.json
├── decision-log.md
└── run-report.json
```

The upstream public concept-design book remains at its approved `persistence_plan.design_book_path` when present. Its internal requirement remains in its sealed version directory and is referenced by hash; legacy packages retain their original locations. Formal output is materialized only after the third confirmation and is never overwritten.

The input requirement must remain with its `asset-catalog.json`, `context-snapshot.json`, and `creative-position.json` companions. The concept-director validator is the sole handoff authority; a standalone JSON object or a copied `fresh` flag is insufficient. It accepts both evidence-backed `accepted` decisions and the user's recorded `user_override` decisions without reopening the user's aesthetic choice.

Presentation uses `design_dimensions.shared.use_case` as `intended_use`, and `design_dimensions.shared.frame` as an object with `framing` and `aspect_ratio`. Legacy string `frame` values supply framing only. Existing confirmed strings take priority over asset-type defaults. Scene states handed to this team must explicitly declare `output_scope: "pure_environment"`; the upstream validator checks their location-master dependency and incompatible participant scope.

`persistence_plan.design_book_path` is an additive revision-2 upstream field. It names the sole public Markdown book for new concept runs and does not change the six-file machine contract. A book path is not valid input to `validate_handoff`; use the internal requirement path and companions, available through materializer `--details` / `machine_handoff`. Validation also requires the recorded source, breakdown, reference-image, and dependency files, so copying a package alone does not make it portable.

Runtime projections are explicit read-only views, not new delivery contracts:

- `RoleRequirementViewV1` removes only `confirmations`, `persistence_plan`, and `integrity`; all design data, evidence, source references, dependency references, constraints, and overrides remain. `source_requirement_hash` is the original requirement file's SHA-256. Evidence, assembly, adversarial, and adjudication roles retain the full requirement.
- `CollaborationContextViewV1` uses `shared_known_ref` pointing to the complete inline `requirement.evidence` only when `shared_known` exactly equals the runtime-generated duplicate. The empty projected `shared_known` means “read the referenced evidence,” not missing evidence. Independent context and added findings remain inline.
- `AgentResultViewV1` identifies an upstream result by its dependency-node key, drops `task_id`, empty metrics, and empty or literal `completed` summaries, and retains substantive summaries, metrics, claims, conflicts, questions, errors, and references.

Unknown fields or unrecognized contracts retain the full input. The canonical sealed requirement remains the authority for validation, hashing, persistence, and confirmed design identity. Dispatch labels each view and explains its references so internal roles do not mistake omitted bookkeeping for an invalid source contract.
