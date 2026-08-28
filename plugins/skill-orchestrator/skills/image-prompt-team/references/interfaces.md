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

The upstream concept-design statement remains in its existing version directory and is referenced by hash. Formal output is materialized only after the third confirmation and is never overwritten.
