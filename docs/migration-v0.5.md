# Migration to v0.5

v0.5 is backward compatible with v0.4 asset and prompt contracts. `RequirementContractV2` now accepts either the legacy `asset_input` or a generic `authoritative_input`, never both.

New semantic types include `scene_direction_requirement_v1`, `director_position_v1`, `scene_direction_package_v1`, `director_knowledge_catalog_v1`, and `director_role_catalog_v1`.

The scene director group requires a validated `screenplay_breakdown_v1`, one or two unique scenes from the same project, first-Grill confirmation before DAG creation, and second-Grill confirmation before sealing. Production codes remain separate from internal stable scene/beat/evidence IDs.

Knowledge starts in `review_pending`. Prompt-director material is indexed as isolated and cannot be published into director role packs.

Install or update from the marketplace, then start a new Codex task so the refreshed skill inventory is loaded.
