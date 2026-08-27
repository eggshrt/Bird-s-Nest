#!/usr/bin/env python3
"""Deterministic helpers for one-asset screenplay concept requirements."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any


ASSET_TYPES = {
    "characters": "character_master",
    "locations": "location_master",
    "props": "hero_prop",
}
REQUIRED_ROLES = {"chief_director", "director", "performance_execution", "art"}
EVIDENCE_KINDS = {"fact", "inference", "design_decision", "preference", "unknown"}
DECISION_STATUSES = {"accepted", "user_override"}
CONFIRMATION_GATES = {"asset_selection", "design_requirement", "persistence_plan"}
REQUIRED_SHARED_DIMENSIONS = {
    "dramatic_function",
    "target_perception",
    "core_proposition",
    "world_culture_basis",
    "recognition_anchors",
    "color_material_use_history",
    "environmental_interaction",
    "use_case",
    "frame",
    "production_limits",
}
REQUIRED_TYPE_DIMENSIONS = {
    "character_master": {
        "growth_stage", "body_proportion", "posture_action_line", "shape_language",
        "silhouette_negative_space", "facial_structure", "skin", "hair_makeup",
        "clothing_layers", "wearing_behavior", "bound_props", "motif_memory_point",
    },
    "location_master": {
        "spatial_function", "geography_circulation", "scale", "architecture",
        "zones", "climate", "life_traces", "light_sources", "materials",
        "institution_regional_culture",
    },
    "scene_state": {
        "location_master_reference", "dramatic_moment", "spatial_changes", "participants",
        "atmosphere", "weather", "time", "lighting", "attention_hierarchy",
        "delta_from_location_master",
    },
    "hero_prop": {
        "owner", "dramatic_use", "operation", "scale", "structure", "mechanism",
        "materials", "weight", "wear", "cultural_origin", "recognition_point",
        "damage_change_states",
    },
}
FORBIDDEN_KEY_PARTS = {
    "prompt",
    "negative_prompt",
    "generation_prompt",
    "model_parameter",
    "provider_syntax",
    "image_generation",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def write_json(payload: Any, path: Path | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not segment or segment in {".", ".."}:
        raise ValueError(f"Unsafe output path segment: {value!r}")
    return segment


def default_analyzer_root() -> Path:
    return Path(__file__).resolve().parents[2] / "ai-script-breakdown"


def hash_tree(root: Path) -> str:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Analyzer root does not exist: {root}")
    digest = hashlib.sha256()
    included = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"} or relative.parts[0] == "tests":
            continue
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        included += 1
    if not included:
        raise ValueError(f"Analyzer root has no versioned files: {root}")
    return digest.hexdigest()


def validate_breakdown_shape(breakdown: dict[str, Any]) -> None:
    required = {"schema_version", "project", "source_manifest", "coverage", "global_analysis", "entities", "scenes", "beats", "ai_feasibility", "role_reports"}
    missing = sorted(required.difference(breakdown))
    if missing:
        raise ValueError("breakdown.json is missing: " + ", ".join(missing))
    if breakdown.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported screenplay breakdown schema")


def state_candidates(record: dict[str, Any], default_id: str, default_label: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    raw = record.get("states") or record.get("state_candidates") or []
    if isinstance(raw, list):
        for index, state in enumerate(raw, start=1):
            if isinstance(state, str) and state.strip():
                candidates.append({"state_id": safe_segment(state), "label": state, "source_refs": []})
            elif isinstance(state, dict):
                state_id = str(state.get("state_id") or state.get("id") or f"state-{index}")
                label = str(state.get("label") or state.get("name") or state_id)
                candidates.append({"state_id": safe_segment(state_id), "label": label, "source_refs": list(state.get("source_refs") or [])})
    if not candidates:
        candidates.append({"state_id": default_id, "label": default_label, "source_refs": list(record.get("source_refs") or [])})
    return candidates


def asset_record(record: dict[str, Any], asset_type: str) -> dict[str, Any]:
    asset_id = str(record.get("id") or "").strip()
    name = str(record.get("name") or record.get("heading") or "").strip()
    if not asset_id or not name:
        raise ValueError(f"Asset record lacks stable id or name: {record}")
    aliases = record.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    scene_ids = list(record.get("scene_ids") or [])
    if asset_type == "scene_state":
        scene_ids = [asset_id]
    defaults = {
        "character_master": ("canonical", "Canonical character state"),
        "location_master": ("canonical", "Canonical location state"),
        "scene_state": ("scene", "Scripted scene state"),
        "hero_prop": ("intact", "Canonical intact state"),
    }
    default_id, default_label = defaults[asset_type]
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "name": name,
        "aliases": sorted({str(item).strip() for item in aliases if str(item).strip()}),
        "source_refs": list(record.get("source_refs") or []),
        "scene_ids": scene_ids,
        "certainty": record.get("certainty", "unknown"),
        "state_candidates": state_candidates(record, default_id, default_label),
    }


def build_catalog(breakdown: dict[str, Any], analyzer_root: Path | None = None) -> dict[str, Any]:
    validate_breakdown_shape(breakdown)
    assets: list[dict[str, Any]] = []
    entities = breakdown["entities"]
    for key, asset_type in ASSET_TYPES.items():
        for record in entities.get(key, []):
            assets.append(asset_record(record, asset_type))
    for scene in breakdown.get("scenes", []):
        assets.append(asset_record(scene, "scene_state"))
    ids = [asset["asset_id"] for asset in assets]
    if len(ids) != len(set(ids)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        raise ValueError("Duplicate stable asset ids: " + ", ".join(duplicates))
    assets.sort(key=lambda item: (item["asset_type"], item["asset_id"]))
    name_groups: dict[str, list[str]] = {}
    for asset in assets:
        for label in [asset["name"], *asset["aliases"]]:
            key = normalize_name(label)
            if key:
                name_groups.setdefault(key, []).append(asset["asset_id"])
    ambiguities = [
        {"normalized_name": key, "asset_ids": sorted(set(asset_ids))}
        for key, asset_ids in sorted(name_groups.items())
        if len(set(asset_ids)) > 1
    ]
    manifest = breakdown["source_manifest"]
    project = breakdown["project"]
    root = analyzer_root or default_analyzer_root()
    return {
        "schema_version": "AssetCatalogV1",
        "project": {"id": project["id"], "title": project.get("title")},
        "draft_id": manifest["draft_id"],
        "source_hash": manifest["sha256"],
        "breakdown_hash": content_hash(breakdown),
        "analyzer_hash": hash_tree(root),
        "assets": assets,
        "ambiguities": ambiguities,
    }


def render_catalog_markdown(catalog: dict[str, Any]) -> str:
    lines = [
        f"# Asset catalog · {catalog['project'].get('title') or catalog['project']['id']}",
        "",
        f"Draft: `{catalog['draft_id']}`  ",
        f"Source: `{catalog['source_hash']}`  ",
        f"Breakdown: `{catalog['breakdown_hash']}`",
        "",
        "| Type | Stable ID | Name | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for asset in catalog["assets"]:
        evidence = ", ".join(asset["source_refs"][:4]) or "unknown"
        lines.append(f"| {asset['asset_type']} | `{asset['asset_id']}` | {asset['name']} | {evidence} |")
    if catalog["ambiguities"]:
        lines.extend(["", "## Ambiguous names", ""])
        for item in catalog["ambiguities"]:
            lines.append(f"- `{item['normalized_name']}`: {', '.join(item['asset_ids'])}")
    return "\n".join(lines) + "\n"


def resolve_asset(catalog: dict[str, Any], query: str, limit: int = 5) -> dict[str, Any]:
    normalized = normalize_name(query)
    if not normalized:
        raise ValueError("Asset query is empty after normalization")
    candidates: list[dict[str, Any]] = []
    for asset in catalog.get("assets", []):
        labels = [asset["asset_id"], asset["name"], *asset.get("aliases", [])]
        normalized_labels = [normalize_name(label) for label in labels]
        if normalized == normalize_name(asset["asset_id"]):
            score, reason = 1.0, "exact_id"
        elif normalized in normalized_labels:
            score, reason = 0.98, "exact_name_or_alias"
        else:
            best = max((SequenceMatcher(None, normalized, label).ratio() for label in normalized_labels if label), default=0.0)
            contains = any(normalized in label or label in normalized for label in normalized_labels if label)
            score = max(best, 0.82 if contains else 0.0)
            reason = "substring" if contains and score == 0.82 else "similarity"
        if score >= 0.45:
            candidates.append({"score": round(score, 4), "reason": reason, **deepcopy(asset)})
    candidates.sort(key=lambda item: (-item["score"], item["asset_type"], item["asset_id"]))
    candidates = candidates[:limit]
    unique_recommendation = bool(candidates) and (
        len(candidates) == 1
        or (candidates[0]["score"] >= 0.98 and candidates[1]["score"] < 0.98)
        or candidates[0]["score"] - candidates[1]["score"] >= 0.12
    )
    return {
        "query": query,
        "normalized_query": normalized,
        "candidates": candidates,
        "recommended_asset_id": candidates[0]["asset_id"] if unique_recommendation else None,
        "confirmation_required": True,
    }


def source_hash(path: Path) -> str:
    text = normalize_text(path.read_text(encoding="utf-8-sig"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freshness_report(
    breakdown: dict[str, Any],
    catalog: dict[str, Any] | None = None,
    source: Path | None = None,
    analyzer_root: Path | None = None,
) -> dict[str, Any]:
    validate_breakdown_shape(breakdown)
    reasons: list[str] = []
    coverage = breakdown["coverage"]
    if coverage.get("status") != "completed":
        reasons.append("coverage_not_completed")
    if coverage.get("pending_scene_ids"):
        reasons.append("pending_scenes")
    if coverage.get("pending_role_ids"):
        reasons.append("pending_roles")
    if not coverage.get("ai_baseline_completed"):
        reasons.append("ai_baseline_incomplete")
    if not coverage.get("cross_role_synthesis_completed"):
        reasons.append("cross_role_synthesis_incomplete")
    completed = set(coverage.get("completed_role_ids") or [])
    reports = {item.get("role_id"): item for item in breakdown.get("role_reports", []) if isinstance(item, dict)}
    for role_id in sorted(REQUIRED_ROLES):
        if role_id not in completed or reports.get(role_id, {}).get("status") != "completed":
            reasons.append(f"required_role_incomplete:{role_id}")
    manifest = breakdown["source_manifest"]
    if manifest.get("extraction_quality") != "good":
        reasons.append(f"extraction_quality:{manifest.get('extraction_quality')}")
    if source is not None and source_hash(source) != manifest.get("sha256"):
        reasons.append("source_hash_changed")
    current_breakdown_hash = content_hash(breakdown)
    current_analyzer_hash = hash_tree(analyzer_root or default_analyzer_root())
    if catalog is not None:
        if catalog.get("source_hash") != manifest.get("sha256"):
            reasons.append("catalog_source_hash_mismatch")
        if catalog.get("breakdown_hash") != current_breakdown_hash:
            reasons.append("catalog_breakdown_hash_mismatch")
        if catalog.get("analyzer_hash") != current_analyzer_hash:
            reasons.append("analyzer_hash_changed")
    return {
        "status": "fresh" if not reasons else "stale",
        "reasons": reasons,
        "source_hash": manifest.get("sha256"),
        "breakdown_hash": current_breakdown_hash,
        "analyzer_hash": current_analyzer_hash,
        "required_roles": sorted(REQUIRED_ROLES),
    }


def _record_mentions(record: Any, asset: dict[str, Any]) -> bool:
    serialized = json.dumps(record, ensure_ascii=False).casefold()
    return asset["asset_id"].casefold() in serialized or asset["name"].casefold() in serialized


def build_snapshot(
    breakdown: dict[str, Any],
    catalog: dict[str, Any],
    asset_id: str,
    *,
    created_at: str | None = None,
    analyzer_root: Path | None = None,
    max_scenes: int = 40,
    max_beats: int = 80,
    max_findings: int = 80,
) -> dict[str, Any]:
    freshness = freshness_report(breakdown, catalog, analyzer_root=analyzer_root)
    if freshness["status"] != "fresh":
        raise ValueError("Baseline is stale: " + ", ".join(freshness["reasons"]))
    matching = [asset for asset in catalog.get("assets", []) if asset.get("asset_id") == asset_id]
    if len(matching) != 1:
        raise ValueError(f"Expected exactly one catalog asset for {asset_id}, found {len(matching)}")
    asset = deepcopy(matching[0])
    relevant_ids = set(asset.get("scene_ids") or [])
    if asset["asset_type"] == "scene_state":
        relevant_ids.add(asset_id)
    for scene in breakdown.get("scenes", []):
        if _record_mentions(scene, asset):
            relevant_ids.add(scene.get("id"))
    all_scenes = [scene for scene in breakdown.get("scenes", []) if scene.get("id") in relevant_ids]
    all_beats = [beat for beat in breakdown.get("beats", []) if beat.get("scene_id") in relevant_ids]
    all_findings: list[dict[str, Any]] = []
    role_deliverables: dict[str, Any] = {}
    for report in breakdown.get("role_reports", []):
        role_id = report.get("role_id")
        if role_id in REQUIRED_ROLES:
            role_deliverables[role_id] = report.get("deliverables", {})
        for finding in report.get("findings", []):
            finding_scenes = set(finding.get("scene_ids") or [])
            if finding_scenes.intersection(relevant_ids) or _record_mentions(finding, asset):
                all_findings.append(finding)
    scenes = all_scenes[:max_scenes]
    beats = all_beats[:max_beats]
    findings = all_findings[:max_findings]
    global_analysis = breakdown["global_analysis"]
    snapshot: dict[str, Any] = {
        "schema_version": "AssetContextSnapshotV1",
        "created_at": created_at or utc_now(),
        "project": {"id": breakdown["project"]["id"], "title": breakdown["project"].get("title")},
        "draft_id": breakdown["source_manifest"]["draft_id"],
        "source_hash": freshness["source_hash"],
        "breakdown_hash": freshness["breakdown_hash"],
        "analyzer_hash": freshness["analyzer_hash"],
        "asset": asset,
        "global_visual_context": {
            "story_contract": global_analysis.get("story_contract", {}),
            "narrative_form": global_analysis.get("narrative_form", {}),
            "character_system": global_analysis.get("character_system", {}),
            "theme_values": global_analysis.get("theme_values", {}),
            "world_rules": global_analysis.get("world_rules", []),
            "continuity": global_analysis.get("continuity", {}),
        },
        "relevant_scenes": scenes,
        "relevant_beats": beats,
        "role_findings": findings,
        "role_deliverables": role_deliverables,
        "ai_feasibility": breakdown.get("ai_feasibility", {}),
        "inclusion": {
            "scene_ids": [item.get("id") for item in scenes],
            "beat_ids": [item.get("id") for item in beats],
            "finding_ids": [item.get("id") for item in findings],
            "omitted_scene_ids": [item.get("id") for item in all_scenes[max_scenes:]],
            "omitted_beat_ids": [item.get("id") for item in all_beats[max_beats:]],
            "omitted_finding_ids": [item.get("id") for item in all_findings[max_findings:]],
            "full_screenplay_included": False,
        },
        "freshness": freshness,
    }
    hash_payload = {key: value for key, value in snapshot.items() if key not in {"created_at", "context_hash"}}
    snapshot["context_hash"] = content_hash(hash_payload)
    return snapshot


def forbidden_keys(payload: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
                found.append(f"{path}.{key}")
            found.extend(forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(forbidden_keys(value, f"{path}[{index}]"))
    return found


def collect_asset_ids(payload: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "asset_id" and isinstance(value, str):
                result.add(value)
            else:
                result.update(collect_asset_ids(value))
    elif isinstance(payload, list):
        for value in payload:
            result.update(collect_asset_ids(value))
    return result


def validate_position(position: dict[str, Any], asset_id: str | None = None) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "asset_id", "claim", "evidence", "aesthetic_preference", "objections", "alternative", "risks", "confidence", "change_conditions", "decision_owner", "human_statement"}
    missing = sorted(required.difference(position))
    if missing:
        errors.append("CreativePositionV1 missing: " + ", ".join(missing))
        return errors
    if position.get("schema_version") != "CreativePositionV1":
        errors.append("creative position schema_version must be CreativePositionV1")
    if asset_id and position.get("asset_id") != asset_id:
        errors.append("creative position asset_id does not match requirement")
    for field in ("claim", "aesthetic_preference", "alternative", "human_statement"):
        if not isinstance(position.get(field), str) or not position[field].strip():
            errors.append(f"creative position {field} must be non-empty")
    for field in ("evidence", "objections", "risks", "change_conditions"):
        if not isinstance(position.get(field), list) or not position[field]:
            errors.append(f"creative position {field} must be a non-empty list")
    if position.get("confidence") not in {"high", "medium", "low"}:
        errors.append("creative position confidence is invalid")
    if position.get("decision_owner") != "user":
        errors.append("creative position decision_owner must be user")
    forbidden = forbidden_keys(position)
    if forbidden:
        errors.append("creative position contains prompt or image-generation fields: " + ", ".join(forbidden))
    return errors


def validate_requirement(
    requirement: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
    position: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "version", "baseline_ref", "asset", "primary_state", "derived_states",
        "design_dimensions", "evidence", "high_impact_decisions", "reference_images",
        "production_constraints", "cultural_boundaries", "invariants", "exclusions",
        "acceptance_criteria", "open_questions", "confirmations",
    }
    missing = sorted(required.difference(requirement))
    if missing:
        errors.append("VisualAssetRequirementV1 missing: " + ", ".join(missing))
        return errors
    if requirement.get("schema_version") != "VisualAssetRequirementV1":
        errors.append("schema_version must be VisualAssetRequirementV1")
    if not re.fullmatch(r"v[1-9][0-9]*", str(requirement.get("version", ""))):
        errors.append("version must look like v1")
    asset = requirement.get("asset") if isinstance(requirement.get("asset"), dict) else {}
    asset_id = asset.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        errors.append("asset.asset_id must be one stable id")
    if asset.get("asset_type") not in set(ASSET_TYPES.values()).union({"scene_state"}):
        errors.append("asset.asset_type is invalid")
    ids = collect_asset_ids(requirement)
    if asset_id and ids != {asset_id}:
        errors.append("requirement contains more than one asset_id")
    primary = requirement.get("primary_state") if isinstance(requirement.get("primary_state"), dict) else {}
    if primary.get("asset_id") != asset_id:
        errors.append("primary_state must belong to the selected asset")
    for field in ("state_id", "label", "design_direction"):
        if not isinstance(primary.get(field), str) or not primary[field].strip():
            errors.append(f"primary_state.{field} must be non-empty")
    for field in ("design_language", "concrete_elements"):
        if not isinstance(primary.get(field), list) or not primary[field]:
            errors.append(f"primary_state.{field} must be a non-empty list")
    state_ids = {primary.get("state_id")}
    derived = requirement.get("derived_states")
    if not isinstance(derived, list):
        errors.append("derived_states must be a list")
        derived = []
    for index, state in enumerate(derived):
        if not isinstance(state, dict):
            errors.append(f"derived_states[{index}] must be an object")
            continue
        if state.get("asset_id") != asset_id:
            errors.append(f"derived_states[{index}] crosses the selected asset")
        if state.get("delta_from") != primary.get("state_id"):
            errors.append(f"derived_states[{index}].delta_from must reference the primary state")
        if not isinstance(state.get("changes"), list) or not state["changes"]:
            errors.append(f"derived_states[{index}].changes must be non-empty")
        state_id = state.get("state_id")
        if state_id in state_ids:
            errors.append(f"duplicate state_id: {state_id}")
        state_ids.add(state_id)
    dimensions = requirement.get("design_dimensions")
    shared_dimensions = dimensions.get("shared") if isinstance(dimensions, dict) else None
    type_dimensions = dimensions.get("type_specific") if isinstance(dimensions, dict) else None
    if not isinstance(shared_dimensions, dict) or not shared_dimensions:
        errors.append("design_dimensions.shared must be a non-empty object")
    else:
        missing_shared = sorted(REQUIRED_SHARED_DIMENSIONS.difference(shared_dimensions))
        if missing_shared:
            errors.append("design_dimensions.shared missing: " + ", ".join(missing_shared))
    if not isinstance(type_dimensions, dict) or not type_dimensions:
        errors.append("design_dimensions.type_specific must be a non-empty object")
    elif asset.get("asset_type") in REQUIRED_TYPE_DIMENSIONS:
        missing_type = sorted(REQUIRED_TYPE_DIMENSIONS[asset["asset_type"]].difference(type_dimensions))
        if missing_type:
            errors.append("design_dimensions.type_specific missing: " + ", ".join(missing_type))
    evidence = requirement.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty list")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or item.get("kind") not in EVIDENCE_KINDS:
                errors.append(f"evidence[{index}].kind is invalid")
                continue
            if not isinstance(item.get("statement"), str) or not item["statement"].strip():
                errors.append(f"evidence[{index}].statement must be non-empty")
            if item.get("kind") in {"fact", "inference"} and not item.get("source_refs"):
                errors.append(f"evidence[{index}] requires source_refs")
    decisions = requirement.get("high_impact_decisions")
    if not isinstance(decisions, list) or not decisions:
        errors.append("high_impact_decisions must be a non-empty list")
    else:
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                errors.append(f"high_impact_decisions[{index}] must be an object")
                continue
            if decision.get("status") not in DECISION_STATUSES:
                errors.append(f"high_impact_decisions[{index}] is not accepted or overridden")
            if not isinstance(decision.get("chosen_option"), str) or not decision.get("chosen_option", "").strip():
                errors.append(f"high_impact_decisions[{index}].chosen_option must be non-empty")
    references = requirement.get("reference_images")
    if not isinstance(references, list):
        errors.append("reference_images must be a list")
    else:
        for index, reference in enumerate(references):
            if not isinstance(reference, dict):
                errors.append(f"reference_images[{index}] must be an object")
                continue
            if reference.get("source") != "user_provided":
                errors.append(f"reference_images[{index}] must be user_provided")
            if not reference.get("controls") or not reference.get("must_not_control"):
                errors.append(f"reference_images[{index}] needs controls and must_not_control")
    if not isinstance(requirement.get("production_constraints"), list) or not requirement["production_constraints"]:
        errors.append("production_constraints must be a non-empty list")
    criteria = requirement.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append("acceptance_criteria must be a non-empty list")
    else:
        for index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict) or not all(criterion.get(key) for key in ("id", "criterion", "method")):
                errors.append(f"acceptance_criteria[{index}] is incomplete")
    if requirement.get("open_questions") != []:
        errors.append("open_questions must be empty")
    confirmations = requirement.get("confirmations")
    confirmed_gates: set[str] = set()
    if not isinstance(confirmations, list):
        errors.append("confirmations must be a list")
    else:
        for item in confirmations:
            if isinstance(item, dict) and item.get("confirmed") is True and item.get("confirmed_at"):
                confirmed_gates.add(item.get("gate"))
        if confirmed_gates != CONFIRMATION_GATES:
            errors.append("all three distinct confirmation gates are required")
    forbidden = forbidden_keys(requirement)
    if forbidden:
        errors.append("prompt or image-generation fields are forbidden: " + ", ".join(forbidden))
    if snapshot is not None:
        if snapshot.get("schema_version") != "AssetContextSnapshotV1":
            errors.append("snapshot schema_version is invalid")
        if snapshot.get("freshness", {}).get("status") != "fresh":
            errors.append("snapshot is stale")
        if snapshot.get("asset", {}).get("asset_id") != asset_id:
            errors.append("snapshot asset does not match requirement")
        snapshot_without_hash = {key: value for key, value in snapshot.items() if key not in {"created_at", "context_hash"}}
        if snapshot.get("context_hash") != content_hash(snapshot_without_hash):
            errors.append("snapshot context_hash does not match its content")
        freshness = snapshot.get("freshness", {})
        for key in ("source_hash", "breakdown_hash", "analyzer_hash"):
            if freshness.get(key) != snapshot.get(key):
                errors.append(f"snapshot freshness.{key} does not match snapshot")
        baseline = requirement.get("baseline_ref") if isinstance(requirement.get("baseline_ref"), dict) else {}
        mapping = {
            "project_id": snapshot.get("project", {}).get("id"),
            "draft_id": snapshot.get("draft_id"),
            "source_hash": snapshot.get("source_hash"),
            "breakdown_hash": snapshot.get("breakdown_hash"),
            "analyzer_hash": snapshot.get("analyzer_hash"),
            "context_hash": snapshot.get("context_hash"),
        }
        for key, expected in mapping.items():
            if baseline.get(key) != expected:
                errors.append(f"baseline_ref.{key} does not match snapshot")
    if position is not None:
        errors.extend(validate_position(position, asset_id))
    return errors


def validate_catalog_snapshot(catalog: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != "AssetCatalogV1":
        errors.append("catalog schema_version must be AssetCatalogV1")
    mapping = {
        "draft_id": snapshot.get("draft_id"),
        "source_hash": snapshot.get("source_hash"),
        "breakdown_hash": snapshot.get("breakdown_hash"),
        "analyzer_hash": snapshot.get("analyzer_hash"),
    }
    for key, expected in mapping.items():
        if catalog.get(key) != expected:
            errors.append(f"catalog {key} does not match snapshot")
    if catalog.get("project", {}).get("id") != snapshot.get("project", {}).get("id"):
        errors.append("catalog project does not match snapshot")
    asset_id = snapshot.get("asset", {}).get("asset_id")
    matching = [asset for asset in catalog.get("assets", []) if isinstance(asset, dict) and asset.get("asset_id") == asset_id]
    if len(matching) != 1 or matching[0] != snapshot.get("asset"):
        errors.append("catalog must contain exactly the selected snapshot asset")
    return errors


def render_requirement_markdown(requirement: dict[str, Any], position: dict[str, Any]) -> str:
    asset = requirement["asset"]
    primary = requirement["primary_state"]
    lines = [
        f"# {asset['name']} · Visual asset requirement {requirement['version']}",
        "",
        f"- Stable asset: `{asset['asset_id']}`",
        f"- Type: `{asset['asset_type']}`",
        f"- Primary state: `{primary['state_id']}` · {primary['label']}",
        "",
        "## Approved direction",
        "",
        primary["design_direction"],
        "",
        "## Design language",
        "",
        *[f"- {item}" for item in primary["design_language"]],
        "",
        "## Concrete elements",
        "",
        *[f"- {item}" for item in primary["concrete_elements"]],
        "",
        "## Director position",
        "",
        position["human_statement"],
    ]
    if requirement["derived_states"]:
        lines.extend(["", "## Derived states", ""])
        for state in requirement["derived_states"]:
            lines.append(f"### {state['label']} (`{state['state_id']}`)")
            lines.append("")
            lines.extend(f"- {change}" for change in state["changes"])
            lines.append("")
    lines.extend(["", "## Invariants", "", *[f"- {item}" for item in requirement["invariants"]]])
    lines.extend(["", "## Exclusions", "", *[f"- {item}" for item in requirement["exclusions"]]])
    lines.extend(["", "## Acceptance criteria", ""])
    for criterion in requirement["acceptance_criteria"]:
        lines.append(f"- **{criterion['id']}** {criterion['criterion']} — {criterion['method']}")
    return "\n".join(lines).rstrip() + "\n"


def render_decision_log(requirement: dict[str, Any]) -> str:
    lines = ["# Decision log", "", "## High-impact decisions", ""]
    for decision in requirement["high_impact_decisions"]:
        lines.append(f"- `{decision.get('id', 'decision')}` **{decision.get('topic', '')}**: {decision['chosen_option']} ({decision['status']}) — {decision.get('consequence', '')}")
    lines.extend(["", "## Confirmations", ""])
    for confirmation in requirement["confirmations"]:
        lines.append(f"- `{confirmation['gate']}` confirmed at {confirmation['confirmed_at']}")
    return "\n".join(lines) + "\n"


def materialize(
    catalog: dict[str, Any],
    snapshot: dict[str, Any],
    requirement: dict[str, Any],
    position: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    errors = validate_catalog_snapshot(catalog, snapshot) + validate_requirement(requirement, snapshot, position)
    if errors:
        raise ValueError("Invalid requirement: " + "; ".join(errors))
    project_id = safe_segment(requirement["baseline_ref"]["project_id"])
    draft_id = safe_segment(requirement["baseline_ref"]["draft_id"])
    asset_id = safe_segment(requirement["asset"]["asset_id"])
    version = safe_segment(requirement["version"])
    project_dir = output_root.resolve() / project_id / draft_id
    version_dir = project_dir / "assets" / asset_id / version
    if version_dir.exists():
        raise ValueError(f"Asset version already exists: {version_dir}")
    version_dir.mkdir(parents=True)
    catalog_json = project_dir / "asset-catalog.json"
    catalog_md = project_dir / "asset-catalog.md"
    write_json(catalog, catalog_json)
    catalog_md.write_text(render_catalog_markdown(catalog), encoding="utf-8")
    outputs = {
        "context_snapshot": version_dir / "context-snapshot.json",
        "requirement_json": version_dir / "requirement.json",
        "requirement_markdown": version_dir / "requirement.md",
        "creative_position": version_dir / "creative-position.json",
        "decision_log": version_dir / "decision-log.md",
    }
    write_json(snapshot, outputs["context_snapshot"])
    write_json(requirement, outputs["requirement_json"])
    write_json(position, outputs["creative_position"])
    outputs["requirement_markdown"].write_text(render_requirement_markdown(requirement, position), encoding="utf-8")
    outputs["decision_log"].write_text(render_decision_log(requirement), encoding="utf-8")
    return {
        "status": "succeeded",
        "asset_id": asset_id,
        "version": version,
        "artifacts": {name: str(path) for name, path in outputs.items()},
        "validation": {"valid": True, "errors": []},
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--breakdown", type=Path, required=True)
    catalog.add_argument("--output", type=Path, required=True)
    catalog.add_argument("--markdown-output", type=Path)
    catalog.add_argument("--analyzer-root", type=Path)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--catalog", type=Path, required=True)
    resolve.add_argument("--query", required=True)
    resolve.add_argument("--limit", type=int, default=5)
    resolve.add_argument("--output", type=Path)
    freshness = commands.add_parser("freshness")
    freshness.add_argument("--breakdown", type=Path, required=True)
    freshness.add_argument("--catalog", type=Path)
    freshness.add_argument("--source", type=Path)
    freshness.add_argument("--analyzer-root", type=Path)
    freshness.add_argument("--output", type=Path)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--breakdown", type=Path, required=True)
    snapshot.add_argument("--catalog", type=Path, required=True)
    snapshot.add_argument("--asset-id", required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate-requirement")
    validate.add_argument("--requirement", type=Path, required=True)
    validate.add_argument("--snapshot", type=Path)
    validate.add_argument("--position", type=Path)
    validate.add_argument("--output", type=Path)
    persist = commands.add_parser("materialize")
    persist.add_argument("--catalog", type=Path, required=True)
    persist.add_argument("--snapshot", type=Path, required=True)
    persist.add_argument("--requirement", type=Path, required=True)
    persist.add_argument("--position", type=Path, required=True)
    persist.add_argument("--output-root", type=Path, required=True)
    persist.add_argument("--output", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "catalog":
            payload = build_catalog(load_json(args.breakdown), args.analyzer_root)
            write_json(payload, args.output)
            if args.markdown_output:
                args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_output.write_text(render_catalog_markdown(payload), encoding="utf-8")
            write_json({"status": "succeeded", "assets": len(payload["assets"]), "output": str(args.output)})
        elif args.command == "resolve":
            write_json(resolve_asset(load_json(args.catalog), args.query, args.limit), args.output)
        elif args.command == "freshness":
            payload = freshness_report(
                load_json(args.breakdown),
                load_json(args.catalog) if args.catalog else None,
                args.source,
                args.analyzer_root,
            )
            write_json(payload, args.output)
            return 0 if payload["status"] == "fresh" else 1
        elif args.command == "snapshot":
            payload = build_snapshot(load_json(args.breakdown), load_json(args.catalog), args.asset_id)
            write_json(payload, args.output)
            write_json({"status": "succeeded", "asset_id": args.asset_id, "context_hash": payload["context_hash"], "output": str(args.output)})
        elif args.command == "validate-requirement":
            errors = validate_requirement(
                load_json(args.requirement),
                load_json(args.snapshot) if args.snapshot else None,
                load_json(args.position) if args.position else None,
            )
            write_json({"valid": not errors, "errors": errors}, args.output)
            return 0 if not errors else 1
        elif args.command == "materialize":
            payload = materialize(
                load_json(args.catalog),
                load_json(args.snapshot),
                load_json(args.requirement),
                load_json(args.position),
                args.output_root,
            )
            write_json(payload, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        write_json({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
