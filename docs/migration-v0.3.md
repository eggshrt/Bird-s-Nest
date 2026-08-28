# v0.3 migration (unpublished development note)

v0.3 was not released. For the public upgrade path, use [migration-v0.4.md](migration-v0.4.md).

v0.3 is an intentionally incompatible runtime upgrade.

## What stays compatible

- `VisualAssetRequirementV1` and the screenplay concept schemas remain unchanged.
- `grill-me` and the pinned `ai-script-breakdown` content remain unchanged.
- Existing screenplay concept output directories remain valid inputs when their contracts are sealed and fresh.

## What is replaced

- `RequirementContractV1` → `RequirementContractV2`
- `ExecutionPlanV1` → `ExecutionGraphV2`
- `RunReportV1` → `RunReportV2`
- The V1 runtime store → a new append-only SQLite event store

The runtime does not import or dual-write V1 data. If the V2 database path contains tables without `schema_meta(version=2)`, startup raises `LegacySchemaError`. The file is not edited or deleted. Move it to a separate backup path if that location is needed for a fresh V2 database.

## Upgrade

1. Keep or fetch tag `v0.2.0` for the frozen previous release.
2. Update the marketplace checkout.
3. Reinstall `skill-orchestrator@skill-orchestrator-private`.
4. Start a new Codex task so the ten Skills are rediscovered.
5. Create new V2 runs. Do not point v0.3 at a V1 run database.

No Git history rewrite is required.
