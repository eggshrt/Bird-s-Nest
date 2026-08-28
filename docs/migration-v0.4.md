# v0.2 → v0.4 migration

v0.3 was an unpublished development waypoint. The next public release after `v0.2.0` is `v0.4.0`.

## Compatible inputs

- Sealed `VisualAssetRequirementV1` remains the only prompt-team input.
- Existing screenplay breakdown and concept-design outputs remain valid when hashes are fresh.
- The SQLite runtime schema remains V2, so old audit databases can be inspected.

## New-run behavior

- New runs require three gates instead of two.
- `ImagePromptPackageV1` is read/export-only.
- New runs write `VisualPromptSpecV1` and `ImagePromptPackageV2`; no design statement is regenerated and no dual-write occurs.
- The old `prompt-architect` Skill remains for historical inspection but is not selected by the v0.4 DAG.
- All six creative experts plus one asset-type expert run on every new task; a reference expert is conditional.

## Upgrade

1. Keep tag `v0.2.0` if the previous behavior is needed.
2. Update the marketplace checkout.
3. Reinstall `skill-orchestrator@skill-orchestrator-private`.
4. Start a new Codex task so all 23 Skills are rediscovered.
5. Create a new v0.4 run from the sealed asset requirement. Do not resume a pre-v0.4 prompt run.

No Git history rewrite or data deletion is required.
