# Stable interfaces

JSON Schemas are in `references/schemas/`. Unknown additive fields are allowed, but the semantic validator remains authoritative for cross-file hashes, single-asset scope, evidence, confirmations, and forbidden prompt-generation fields.

## AssetCatalogV1

Project-level selection inventory derived from one `screenplay_breakdown_v1`:

```json
{
  "schema_version": "AssetCatalogV1",
  "project": {"id": "project", "title": "Title"},
  "draft_id": "draft-1",
  "source_hash": "sha256",
  "breakdown_hash": "sha256",
  "analyzer_hash": "sha256",
  "assets": [{
    "asset_id": "chr-001",
    "asset_type": "character_master",
    "name": "Character",
    "aliases": [],
    "source_refs": ["L1-L4"],
    "scene_ids": ["scn-001"],
    "certainty": "explicit",
    "state_candidates": [{"state_id": "canonical", "label": "Canonical", "source_refs": []}]
  }],
  "ambiguities": []
}
```

## AssetContextSnapshotV1

A fresh, bounded, disk-derived context for exactly one selected asset. It carries the same source, breakdown, and analyzer hashes as the catalog and records included and omitted evidence.

## VisualAssetRequirementV1

The only approved downstream handoff:

```json
{
  "schema_version": "VisualAssetRequirementV1",
  "version": "v1",
  "baseline_ref": {
    "project_id": "project",
    "draft_id": "draft-1",
    "source_hash": "sha256",
    "breakdown_hash": "sha256",
    "analyzer_hash": "sha256",
    "context_hash": "sha256"
  },
  "asset": {"asset_id": "chr-001", "asset_type": "character_master", "name": "Character"},
  "primary_state": {
    "state_id": "canonical",
    "asset_id": "chr-001",
    "label": "Canonical",
    "design_direction": "One approved direction",
    "design_language": ["observable rule"],
    "concrete_elements": ["visible element"]
  },
  "derived_states": [{
    "state_id": "injured",
    "asset_id": "chr-001",
    "label": "After injury",
    "delta_from": "canonical",
    "changes": ["observable delta"],
    "source_refs": ["L80-L92"]
  }],
  "design_dimensions": {"shared": {}, "type_specific": {}},
  "evidence": [{"kind": "fact", "statement": "Evidence", "source_refs": ["L1-L4"], "confidence": "high"}],
  "high_impact_decisions": [{"id": "D1", "topic": "Silhouette", "chosen_option": "A", "status": "accepted", "consequence": "Readable at distance"}],
  "reference_images": [],
  "production_constraints": [],
  "cultural_boundaries": [],
  "invariants": [],
  "exclusions": [],
  "acceptance_criteria": [{"id": "AC-1", "criterion": "Observable condition", "method": "Human review"}],
  "open_questions": [],
  "confirmations": [
    {"gate": "asset_selection", "confirmed": true, "confirmed_at": "ISO-8601"},
    {"gate": "design_requirement", "confirmed": true, "confirmed_at": "ISO-8601"},
    {"gate": "persistence_plan", "confirmed": true, "confirmed_at": "ISO-8601"}
  ]
}
```

Evidence kinds are `fact`, `inference`, `design_decision`, `preference`, or `unknown`. Facts and inferences require source references. Derived states must use the primary asset id and contain deltas only.

## CreativePositionV1

```json
{
  "schema_version": "CreativePositionV1",
  "asset_id": "chr-001",
  "claim": "One preferred direction",
  "evidence": ["L1-L4"],
  "aesthetic_preference": "Why it is visually stronger",
  "objections": ["Rejected default"],
  "alternative": "Best fallback",
  "risks": ["Tradeoff"],
  "confidence": "high",
  "change_conditions": ["New evidence that changes the position"],
  "decision_owner": "user",
  "human_statement": "Concise debate-ready statement."
}
```

The card records an independent position; it does not authorize a subagent or claim consensus.
