# Stable interfaces

JSON Schemas are in `references/schemas/`. Run schema validation and the shared semantic validator: schema shape alone does not prove source freshness, single-subject identity, evidence coverage, dependency integrity, or user approval. Final validation requires the snapshot and creative-position sidecars and rechecks their disk sources.

## AssetCatalogV1

A project-level selection inventory derived from one validated `screenplay_breakdown_v1`. Each record contains `asset_id`, `asset_type`, `name`, `aliases`, `source_refs`, `scene_ids`, `certainty`, and `state_candidates`. The catalog carries project/draft identifiers plus source, breakdown, and analyzer hashes. Catalog creation copies verified analysis provenance; it cannot declare an old breakdown analyzed with today's analyzer.

## AssetContextSnapshotV1

A fresh disk-derived context for exactly one proposed subject. It carries the catalog's project/draft identity and source, breakdown, and analyzer hashes, along with:

- `baseline_files.breakdown_path` and `baseline_files.source_path` for revalidation;
- the complete selected catalog record and selected-asset scene/beat/role evidence;
- project summaries, relevant cross-role decisions, issues, and handoff blockers;
- `evidence_completeness` and omission accounting.

No complete screenplay body is permitted. Freshness and completeness are separate: omitted required evidence or an exceeded budget blocks delivery. The requirement's `baseline_ref.context_hash` binds the exact snapshot.

## VisualAssetRequirementV1

The downstream handoff retains `schema_version: VisualAssetRequirementV1` and requires `contract_revision: 2`. Legacy unbound V1 confirmations are drafts, not approved handoffs; review their contents and collect content-bound confirmations rather than migrating approval automatically.

| Field | Meaning |
| --- | --- |
| `version` | New package version, never an overwrite |
| `baseline_ref` | `project_id`, `draft_id`, `source_hash`, `breakdown_hash`, `analyzer_hash`, `context_hash` |
| `asset` | Exact catalog `asset_id`, `asset_type`, and `name` |
| `primary_state` | One `state_id`, same `asset_id`, label, approved direction, visual grammar, and concrete elements |
| `derived_states` | Same subject, unique state ids, `delta_from` primary, label, source refs, and changes only |
| `design_dimensions` | Resolved shared and type-specific dimensions from the design method |
| `evidence` | Traceable facts/inferences, explicit design decisions/preferences, and non-consequential unknowns |
| `high_impact_decisions` | Decision id, topic, chosen option, consequence, and `accepted` or `user_override` status |
| `reference_images` | References with explicit `controls` and `must_not_control` |
| `dependency_assets` | Versioned, hash-bound, read-only requirements, or an empty list |
| `output_scope` | `pure_environment` for `location_master` and `scene_state` |
| `creative_position_hash` | Hash of the accompanying `CreativePositionV1` |
| `production_constraints`, `cultural_boundaries`, `invariants`, `exclusions` | Concrete constraints and boundaries |
| `acceptance_criteria` | Observable criterion and verification method for each criterion id |
| `open_questions` | Empty at approval and delivery |
| `persistence_plan` | Internal `output_root`, six canonical files, validators, and approved public `design_book_path` for new runs |
| `confirmations` | Three distinct user approvals bound to their content |
| `integrity.requirement_hash` | Computed seal; does not confer approval |

Evidence kinds are `fact`, `inference`, `design_decision`, `preference`, or `unknown`. Fact/inference references must resolve to included baseline evidence; a nonempty invented reference is invalid. `unknown` cannot stand in for an unresolved consequential choice. Use a structured `not_applicable` status and explicit reason only when a dimension does not affect the requested design.

`user_override` is an approved choice with a different origin, not a pending decision. Preserve the director's original recommendation, the user's choice, its consequence, and approval evidence. Downstream may change expression and emphasis; changing the confirmed design requires renewed concept approval.

### Design book and internal handoff

`persistence_plan.design_book_path` is an absolute `.md` path, separate from internal `output_root`. It is optional only for backward compatibility with existing sealed revision-2 packages; every new run must include it. Its presence opts into publishing the single public Chinese design book. It is covered by Gate 3's persistence digest and cannot be overridden by a separate CLI destination flag.

The six internal files and their order stay unchanged. They include deterministic `requirement.md` and `decision-log.md` for internal compatibility; these are not additional user deliverables. The script renders the public book from the same approved canonical records, including the complete creative position, tradeoffs, overrides, confirmation summary, and a folded evidence appendix. No second model-authored prose pass is required.

Existing sealed revision-2 packages without this field remain readable, validatable, and usable for handoff in their legacy six-file layout. They can materialize into an absent approved version directory. Completed packages remain immutable: if an older renderer produced different Markdown, a new materialization attempt rejects while the original package remains usable. Do not move it or add a publication destination without renewed persistence approval. Packages retain absolute source/baseline/dependency references and require those files for revalidation; the public book is a reading artifact, not a replacement machine contract.

Default materialization output exposes the public `deliverables` and status/identity/validation summary. `--details` additionally exposes internal artifacts and `machine_handoff` for automation. Downstream roles receive a compact projection without runtime metadata, while all evidence and constraints remain available and handoff validation always uses the original sealed package.

### Read-only dependencies and environment scope

A dependency has this shape:

```json
{
  "ref_asset_id": "loc-001",
  "asset_type": "location_master",
  "version": "v1",
  "requirement_path": "/absolute/path/to/requirement.json",
  "requirement_hash": "sha256"
}
```

The referenced requirement must exist and match identity, type, version, and hash. Use `ref_asset_id`, not nested `asset_id`, to distinguish a reference from the current creative subject. A scene state references its exact location master through this list and sets `design_dimensions.type_specific.location_master_reference` to that dependency's `ref_asset_id`; prose naming alone does not bind a master. Dependency changes require revalidation and new affected approvals. They never authorize modifying another asset.

For `scene_state`, participants, power relations, and dramatic purpose may explain the environment's design, but the handoff must explicitly specify `output_scope: pure_environment`. A request to depict participants, performance, or blocking belongs to `$screenplay-scene-daoyanzu`. Do not omit those requested elements merely to satisfy this contract.

### Confirmation binding

Each gate has one record:

```json
{
  "gate": "design_requirement",
  "confirmed": true,
  "confirmed_at": "2026-09-21T12:00:00+08:00",
  "confirmed_by": "user",
  "message_ref": "actual-user-message-reference",
  "content_hash": "digest-of-the-approved-content"
}
```

The example is a shape, not an approval. Only a real user message may establish a record; three `true` values or generated timestamps cannot create consent. `confirmation-digest` computes the expected content hash and never fills approval fields.

- `asset_selection` binds `asset` and `baseline_ref` excluding `context_hash`; the later snapshot hash is bound by the design confirmation.
- `design_requirement` binds the requirement excluding `confirmations`, `persistence_plan`, and `integrity`; this includes the creative-position hash and dependency references.
- `persistence_plan` binds the design digest and the exact persistence plan.

Changed identity/baseline invalidates every gate. Changed design, dependency, or creative position invalidates Gate 2 and Gate 3. Changed destination/files/validators invalidates Gate 3. Reconfirm changed content; never silently recalculate an old user's approval. Timestamps must be valid and gate approvals must be distinct, ordered user decisions. Hash binding detects content drift but is not cryptographic proof of who spoke; retain verifiable conversation references.

## CreativePositionV1

The card contains `asset_id`, `claim`, source-referenced `evidence`, `aesthetic_preference`, `objections`, `alternative`, `risks`, `confidence`, `change_conditions`, `decision_owner: user`, and a concise `human_statement`. It records the director's independent position, even when the user overrides it. It neither authorizes subagents nor claims team consensus. The requirement binds its full contents through `creative_position_hash`.
