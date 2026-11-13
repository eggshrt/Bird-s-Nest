#!/usr/bin/env python3
"""Deterministic helpers for one-asset screenplay concept requirements."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_schema import validate_file as schema_errors

PACKAGE_FILES = ['context-snapshot.json', 'requirement.json', 'requirement.md',
                 'creative-position.json', 'decision-log.md', 'asset-catalog.json']
VALIDATORS = ['schema', 'semantic', 'disk_freshness']


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
    segment = ''.join(char if char.isalnum() or char in '._-' else '-' for char in unicodedata.normalize('NFC', value.strip())).strip('-.')
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
    fresh = freshness_report(breakdown, analyzer_root=analyzer_root)
    if fresh['status'] != 'fresh':
        raise ValueError('Baseline requires reanalysis: ' + ', '.join(fresh['reasons']))
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


def valid_timestamp(value: Any) -> bool:
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace('Z', '+00:00')).utcoffset() is not None
    except (ValueError, TypeError):
        return False


def strip_source_body(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_source_body(child) for key, child in value.items()
                if key not in {'text', 'raw_text', 'source_text', 'full_text', 'screenplay', 'dialogue'}}
    if isinstance(value, list):
        return [strip_source_body(child) for child in value]
    return deepcopy(value)


def source_ref_bounds(breakdown: dict) -> dict[str, int]:
    manifest = breakdown['source_manifest']
    text = normalize_text(Path(manifest['analysis_provenance']['source_path']).read_text(encoding='utf-8-sig'))
    if manifest['format'] == 'fdx':
        import xml.etree.ElementTree as ET
        return {'P': sum(1 for p in ET.fromstring(text).iter() if p.tag.rsplit('}', 1)[-1] == 'Paragraph')}
    return {'L': len(text.splitlines())}


def reference_errors(refs: Any, snapshot: dict, label: str) -> list[str]:
    errors = []
    pattern = r'([LP])([1-9][0-9]*)(?:-\1?([1-9][0-9]*))?'
    included = []
    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'source_refs' and isinstance(child, list):
                    included.extend(child)
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(snapshot)
    ranges = [re.fullmatch(pattern, ref) for ref in included if isinstance(ref, str)]
    for ref in refs if isinstance(refs, list) else [refs]:
        match = re.fullmatch(pattern, ref) if isinstance(ref, str) else None
        if match is None:
            errors.append(f'{label}: unresolvable source reference {ref!r}')
        else:
            start, end = int(match[2]), int(match[3] or match[2])
            if not 1 <= start <= end <= snapshot.get('source_ref_bounds', {}).get(match[1], 0):
                errors.append(f'{label}: source reference outside source bounds: {ref}')
            elif not any(r and r[1] == match[1] and int(r[2]) <= start <= end <= int(r[3] or r[2]) for r in ranges):
                errors.append(f'{label}: source reference is absent from included snapshot evidence: {ref}')
    return errors


def refs_overlap(left: list, right: list) -> bool:
    pattern = r'([LP])([1-9][0-9]*)(?:-\1?([1-9][0-9]*))?'
    for a in left:
        am = re.fullmatch(pattern, a) if isinstance(a, str) else None
        for b in right:
            bm = re.fullmatch(pattern, b) if isinstance(b, str) else None
            if am and bm and am[1] == bm[1] and max(int(am[2]), int(bm[2])) <= min(int(am[3] or am[2]), int(bm[3] or bm[2])):
                return True
    return False


def requirement_hash(requirement: dict) -> str:
    return content_hash({k: v for k, v in requirement.items() if k != 'integrity'})


def resolved_dimension(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() not in {'unknown', 'tbd', 'pending', 'unresolved', 'not_applicable'}
    if isinstance(value, list):
        return bool(value) and all(resolved_dimension(child) for child in value)
    if isinstance(value, dict):
        if value.get('status') == 'not_applicable':
            return set(value) == {'status', 'reason'} and isinstance(value['reason'], str) and bool(value['reason'].strip()) and resolved_dimension(value['reason'])
        return bool(value) and all(resolved_dimension(child) for child in value.values())
    return False


def confirmation_hash(requirement: dict, gate: str) -> str:
    if gate == 'asset_selection':
        payload = {'asset': requirement['asset'], 'baseline_ref': {k: v for k, v in requirement['baseline_ref'].items() if k != 'context_hash'}}
    elif gate == 'design_requirement':
        payload = {k: v for k, v in requirement.items() if k not in {'confirmations', 'persistence_plan', 'integrity'}}
    elif gate == 'persistence_plan':
        payload = {'design_hash': confirmation_hash(requirement, 'design_requirement'),
                   'persistence_plan': requirement['persistence_plan']}
    else:
        raise ValueError('Unknown confirmation gate')
    return content_hash(payload)


def seal_requirement(requirement: dict, snapshot: dict, position: dict, *, analyzer_root: Path | None = None) -> dict:
    sealed = deepcopy(requirement)
    sealed['integrity'] = {'requirement_hash': requirement_hash(sealed)}
    errors = validate_requirement(sealed, snapshot, position, analyzer_root=analyzer_root)
    if errors:
        raise ValueError('Cannot seal requirement: ' + '; '.join(errors))
    return sealed


def freshness_report(
    breakdown: dict[str, Any],
    catalog: dict[str, Any] | None = None,
    source: Path | None = None,
    analyzer_root: Path | None = None,
) -> dict[str, Any]:
    validate_breakdown_shape(breakdown)
    reasons: list[str] = []
    spec = importlib.util.spec_from_file_location('_concept_upstream_validator', default_analyzer_root() / 'scripts/validate_breakdown.py')
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    try:
        reasons.extend('breakdown_invalid:' + error for error in validator.validate_breakdown(breakdown).errors)
    except (TypeError, KeyError, AttributeError) as exc:
        reasons.append('breakdown_invalid:' + str(exc))
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
    current_breakdown_hash = content_hash(breakdown)
    current_analyzer_hash = hash_tree(analyzer_root or default_analyzer_root())
    provenance = manifest.get('analysis_provenance') or {}
    if not isinstance(provenance, dict):
        provenance = {}
    if provenance.get('analyzer_hash') != current_analyzer_hash:
        reasons.append('analysis_analyzer_changed_or_unrecorded:reanalysis_required')
    if provenance.get('source_hash') != manifest.get('sha256'):
        reasons.append('analysis_source_hash_mismatch')
    if not valid_timestamp(provenance.get('captured_at')):
        reasons.append('analysis_capture_time_missing_or_invalid')
    recorded_source = provenance.get('source_path')
    if not isinstance(recorded_source, str) or not Path(recorded_source).is_absolute():
        reasons.append('source_path_unverified:normalize_a_persisted_source_at_intake')
    else:
        source_path = Path(recorded_source)
        if source is not None and source.resolve() != source_path.resolve():
            reasons.append('source_path_mismatch')
        try:
            if source_hash(source_path) != manifest.get('sha256'):
                reasons.append('source_hash_changed')
        except (OSError, UnicodeError):
            reasons.append('source_unavailable')
    if provenance.get('original_source_path') or provenance.get('original_source_hash'):
        try:
            original = Path(provenance['original_source_path'])
            if not original.is_absolute() or hashlib.sha256(original.read_bytes()).hexdigest() != provenance.get('original_source_hash'):
                reasons.append('original_document_changed:reextract_and_reanalyze')
        except (OSError, KeyError, TypeError):
            reasons.append('original_document_unavailable')
    all_scene_ids = {s.get('id') for s in breakdown.get('scenes', []) if isinstance(s, dict)}
    if set(coverage.get('completed_scene_ids') or []) != all_scene_ids:
        reasons.append('whole_screenplay_coverage_incomplete')
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
    return any(str(label).casefold() in serialized for label in [asset['asset_id'], asset['name'], *asset.get('aliases', [])] if label)


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
    breakdown_path: Path | None = None,
    max_context_bytes: int = 200000,
) -> dict[str, Any]:
    freshness = freshness_report(breakdown, catalog, analyzer_root=analyzer_root)
    if freshness["status"] != "fresh":
        raise ValueError("Baseline is stale: " + ", ".join(freshness["reasons"]))
    if breakdown_path is None or content_hash(load_json(breakdown_path)) != content_hash(breakdown):
        raise ValueError('Snapshot requires the current breakdown_path on disk')
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
    relevant_beat_ids = {beat['id'] for beat in all_beats}
    relevant_refs = [ref for record in [asset, *all_scenes, *all_beats] for ref in record.get('source_refs', [])]
    def related(record: dict) -> bool:
        return bool(set(record.get('scene_ids') or []).intersection(relevant_ids)
                    or set(record.get('beat_ids') or []).intersection(relevant_beat_ids)
                    or _record_mentions(record, asset)
                    or refs_overlap(record.get('source_refs') or [], relevant_refs))
    all_findings: list[dict[str, Any]] = []
    role_deliverables: dict[str, Any] = {}
    for report in breakdown.get("role_reports", []):
        role_id = report.get("role_id")
        if role_id in REQUIRED_ROLES:
            role_deliverables[role_id] = report.get("deliverables", {})
        for finding in report.get("findings", []):
            if related(finding):
                all_findings.append(finding)
    if len(all_scenes) > max_scenes or len(all_beats) > max_beats or len(all_findings) > max_findings:
        raise ValueError('Evidence budget exceeded; increase the explicit budget or create a reviewed bounded baseline summary. No evidence was truncated.')
    scenes, beats, findings = map(strip_source_body, (all_scenes, all_beats, all_findings))
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
        "limits": {'max_scenes': max_scenes, 'max_beats': max_beats, 'max_findings': max_findings, 'max_context_bytes': max_context_bytes},
        "baseline_files": {'breakdown_path': str(breakdown_path.resolve()),
                           'source_path': breakdown['source_manifest']['analysis_provenance']['source_path']},
        "source_ref_bounds": source_ref_bounds(breakdown),
        "cross_role_decisions": strip_source_body(breakdown.get('cross_role_decisions', [])),
        "issues": strip_source_body([item for item in breakdown.get('issues', []) if related(item) or not any(item.get(k) for k in ('source_refs', 'scene_ids', 'beat_ids'))]),
        "handoff": strip_source_body(breakdown.get('handoff', {})),
        "evidence_completeness": {'status': 'complete', 'omitted_ids': []},
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
        "role_deliverables": strip_source_body(role_deliverables),
        "ai_feasibility": strip_source_body(breakdown.get("ai_feasibility", {})),
        "role_blockers": {report['role_id']: report.get('blockers', []) for report in breakdown['role_reports'] if report.get('blockers')},
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
    snapshot['global_visual_context'] = strip_source_body(snapshot['global_visual_context'])
    if len(canonical_bytes(snapshot)) > max_context_bytes:
        raise ValueError('Context exceeds the explicit byte budget; no incomplete snapshot was created')
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
    errors: list[str] = schema_errors(position, 'creative-position-v1.schema.json')
    if errors:
        return errors
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
    *, analyzer_root: Path | None = None,
    _seen: frozenset[str] = frozenset(),
) -> list[str]:
    errors: list[str] = schema_errors(requirement, 'visual-asset-requirement-v1.schema.json')
    if snapshot is None or position is None:
        errors.append('Formal validation requires context snapshot and creative position; legacy packages need revalidation and confirmation')
    else:
        errors.extend(schema_errors(snapshot, 'asset-context-snapshot-v1.schema.json'))
        errors.extend(schema_errors(position, 'creative-position-v1.schema.json'))
    if errors:
        return errors
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
    for group in (shared_dimensions, type_dimensions):
        for key, value in (group or {}).items():
            if not resolved_dimension(value):
                errors.append(f'design dimension {key} is unresolved')
    if asset['asset_type'] in {'location_master', 'scene_state'} and requirement.get('output_scope') != 'pure_environment':
        errors.append('Environment handoff requires explicit pure_environment scope; route narrative scenes to scene direction')
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
            errors.extend(reference_errors(item.get('source_refs'), snapshot, f'evidence[{index}]'))
    for index, state in enumerate(derived):
        errors.extend(reference_errors(state['source_refs'], snapshot, f'derived_states[{index}]'))
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
            if decision.get('status') == 'user_override' and not decision.get('original_recommendation'):
                errors.append(f'high_impact_decisions[{index}] user_override requires original_recommendation')
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
            try:
                if not Path(reference['path']).is_absolute() or hashlib.sha256(Path(reference['path']).read_bytes()).hexdigest() != reference['sha256']:
                    errors.append(f'reference_images[{index}] path or hash mismatch')
            except OSError:
                errors.append(f'reference_images[{index}] unavailable')
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
    seen_messages, times = set(), []
    ordered_gates = ['asset_selection', 'design_requirement', 'persistence_plan']
    if [c['gate'] for c in confirmations] != ordered_gates:
        errors.append('Confirmations must be three distinct gates in workflow order')
    for item in confirmations:
        if item['message_ref'] in seen_messages:
            errors.append('Each gate must cite its distinct actual user confirmation')
        seen_messages.add(item['message_ref'])
        if not valid_timestamp(item['confirmed_at']):
            errors.append('Confirmation timestamp must be timezone-aware ISO-8601')
        else:
            times.append(datetime.fromisoformat(item['confirmed_at'].replace('Z', '+00:00')))
        if item['content_hash'] != confirmation_hash(requirement, item['gate']):
            errors.append(f"{item['gate']} confirmation no longer matches its approved content")
    if times != sorted(times):
        errors.append('Confirmation timestamps are out of order')
    if requirement['integrity']['requirement_hash'] != requirement_hash(requirement):
        errors.append('Sealed requirement hash does not match its content')
    if requirement['creative_position_hash'] != content_hash(position):
        errors.append('Creative position changed since design confirmation')
    plan = requirement['persistence_plan']
    if not Path(plan['output_root']).is_absolute() or plan['files'] != PACKAGE_FILES or plan['validators'] != VALIDATORS:
        errors.append('Persistence plan must name an absolute output_root, exact package files and validators')
    if 'design_book_path' in plan:
        book = Path(plan['design_book_path'])
        if not book.is_absolute() or book.suffix.lower() != '.md':
            errors.append('design_book_path must be an absolute Markdown file path')
        if book.resolve().is_relative_to(Path(plan['output_root']).resolve()):
            errors.append('design_book_path must be outside the internal package root')
    forbidden = forbidden_keys(requirement)
    if forbidden:
        errors.append("prompt or image-generation fields are forbidden: " + ", ".join(forbidden))
    if snapshot is not None:
        if not valid_timestamp(snapshot.get('created_at')):
            errors.append('Snapshot timestamp must be timezone-aware ISO-8601')
        if snapshot.get("schema_version") != "AssetContextSnapshotV1":
            errors.append("snapshot schema_version is invalid")
        if snapshot.get("freshness", {}).get("status") != "fresh":
            errors.append("snapshot is stale")
        if snapshot.get("asset", {}).get("asset_id") != asset_id:
            errors.append("snapshot asset does not match requirement")
        for key in ('asset_type', 'name'):
            if snapshot['asset'].get(key) != asset.get(key):
                errors.append(f'snapshot asset {key} does not match requirement')
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
        try:
            disk_breakdown = load_json(Path(snapshot['baseline_files']['breakdown_path']))
            disk_catalog = build_catalog(disk_breakdown, analyzer_root)
            rebuilt = build_snapshot(disk_breakdown, disk_catalog, asset_id,
                                     breakdown_path=Path(snapshot['baseline_files']['breakdown_path']),
                                     analyzer_root=analyzer_root, **snapshot.get('limits', {}))
            if rebuilt['context_hash'] != snapshot['context_hash']:
                errors.append('Snapshot no longer matches the complete current disk baseline')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append('Disk baseline validation failed: ' + str(exc))
        if snapshot.get('role_blockers') or snapshot.get('handoff', {}).get('blocked_by') or snapshot.get('ai_feasibility', {}).get('blockers'):
            errors.append('Baseline has unresolved production/handoff blockers')
        if any(finding.get('severity') == 'blocker' for finding in snapshot['role_findings'] + snapshot['issues']):
            errors.append('Selected-asset evidence contains a blocker finding; resolve it in the baseline before handoff')
    if position is not None:
        errors.extend(validate_position(position, asset_id))
        errors.extend(reference_errors(position['evidence'], snapshot, 'creative_position.evidence'))
    dependencies = requirement['dependency_assets']
    dep_ids = [dep['ref_asset_id'] for dep in dependencies]
    if len(dep_ids) != len(set(dep_ids)) or asset_id in dep_ids:
        errors.append('Dependency references must be unique and cannot reference self')
    if asset['asset_type'] == 'scene_state':
        master = type_dimensions.get('location_master_reference')
        if not any(dep['ref_asset_id'] == master and dep['asset_type'] == 'location_master' for dep in dependencies):
            errors.append('scene_state requires a sealed version/hash-bound location_master dependency')
    for dep in dependencies:
        try:
            path = Path(dep['requirement_path'])
            if not path.is_absolute():
                raise ValueError('dependency path must be absolute')
            target = load_json(path)
            if dep['requirement_hash'] != requirement_hash(target) or target.get('version') != dep['version'] or target.get('asset', {}).get('asset_id') != dep['ref_asset_id'] or target.get('asset', {}).get('asset_type') != dep['asset_type']:
                raise ValueError('dependency identity/version/hash changed')
            errors.extend('dependency: ' + e for e in validate_handoff(target, path, _seen=_seen))
        except (ValueError, OSError, KeyError) as exc:
            errors.append('Invalid dependency: ' + str(exc))
    return errors


def validate_handoff(requirement: dict, requirement_path: Path | None = None, *, _seen: frozenset[str] = frozenset()) -> list[str]:
    if requirement_path is None:
        return ['Sealed handoff requires requirement_path and its catalog, snapshot and position sidecars']
    path = requirement_path.resolve()
    if str(path) in _seen or len(_seen) >= 8:
        return ['Cyclic or excessively deep asset dependency']
    try:
        if load_json(path) != requirement:
            return ['Handoff payload differs from its file']
        snapshot = load_json(path.parent / 'context-snapshot.json')
        position = load_json(path.parent / 'creative-position.json')
        catalog = load_json(path.parent / 'asset-catalog.json')
        return validate_catalog_snapshot(catalog, snapshot) + validate_requirement(requirement, snapshot, position, _seen=_seen | {str(path)})
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return ['Invalid handoff package: ' + str(exc)]


def validate_catalog_snapshot(catalog: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = schema_errors(catalog, 'asset-catalog-v1.schema.json') + schema_errors(snapshot, 'asset-context-snapshot-v1.schema.json')
    if errors:
        return errors
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


def _concept_label(key: str) -> str:
    labels = {
        "shared": "通用设计维度", "type_specific": "资产专属设计维度",
        "dramatic_function": "戏剧功能", "target_perception": "目标观众感受",
        "core_proposition": "核心命题", "world_culture_basis": "世界与文化依据",
        "recognition_anchors": "识别锚点", "color_material_use_history": "色彩、材质与使用历史",
        "environmental_interaction": "环境互动", "use_case": "使用场景",
        "frame": "画幅与呈现范围", "production_limits": "制作限制",
        "growth_stage": "人物成长阶段", "body_proportion": "身体比例",
        "posture_action_line": "姿态与动作线", "shape_language": "形状语言",
        "silhouette_negative_space": "剪影与负空间", "facial_structure": "面部结构",
        "skin": "皮肤状态", "hair_makeup": "发型与妆容", "clothing_layers": "服装层次",
        "wearing_behavior": "穿戴行为", "bound_props": "绑定道具", "motif_memory_point": "母题与记忆点",
        "spatial_function": "空间功能", "geography_circulation": "地理与动线", "scale": "尺度",
        "architecture": "建筑逻辑", "zones": "空间分区", "climate": "气候",
        "life_traces": "生活与使用痕迹", "light_sources": "实际光源", "materials": "材质",
        "institution_regional_culture": "制度与地域文化", "location_master_reference": "场景母版引用",
        "dramatic_moment": "戏剧时刻", "spatial_changes": "空间变化", "participants": "人物关系背景",
        "atmosphere": "氛围", "weather": "天气", "time": "时间", "lighting": "照明",
        "attention_hierarchy": "注意力层级", "delta_from_location_master": "相对场景母版的变化",
        "owner": "所有者或保管者", "dramatic_use": "戏剧用途", "operation": "操作方式",
        "structure": "结构", "mechanism": "机制", "weight": "重量感", "wear": "磨损",
        "cultural_origin": "文化来源", "recognition_point": "识别点", "damage_change_states": "损伤与变化状态",
        "status": "状态", "reason": "原因", "description": "说明", "value": "设计值",
        "primary": "主要", "secondary": "次要", "color": "色彩", "material": "材质",
        "palette": "色板", "layers": "层次", "name": "名称", "notes": "备注",
        "id": "编号", "topic": "议题", "chosen_option": "最终选择", "consequence": "后果与取舍",
        "original_recommendation": "导演原建议", "approval_evidence": "确认依据", "message_ref": "用户消息引用",
        "source_refs": "来源引用", "confirmed": "已确认", "confirmed_at": "确认时间",
        "confirmed_by": "确认人", "content_hash": "确认内容摘要", "schema_version": "接口版本",
        "contract_revision": "契约修订", "asset_id": "资产编号", "project_id": "项目编号",
        "draft_id": "剧本稿次", "version": "资产版本", "source_hash": "源文件摘要",
        "breakdown_hash": "分析基线摘要", "analyzer_hash": "分析器摘要", "context_hash": "上下文快照摘要",
        "creative_position_hash": "导演立场摘要", "requirement_hash": "需求内容摘要",
        "output_root": "后台资料根目录", "design_book_path": "公开设计书路径", "files": "文件清单", "validators": "校验器",
        "framing": "构图与取景", "aspect_ratio": "宽高比", "intended_use": "预期用途",
        "path": "路径", "source": "来源", "sha256": "文件摘要", "requirement_path": "需求文件路径",
        "ref_asset_id": "依赖资产编号", "asset_type": "资产类型",
    }
    return labels.get(key, key)


def _concept_text(value: Any) -> str:
    if value is None:
        return "未提供"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _concept_value(value: Any, depth: int = 0) -> list[str]:
    """Render every canonical value as readable nested Markdown, without rewriting it."""
    prefix = "    " * depth
    if isinstance(value, dict):
        if not value:
            return [prefix + "- 无"]
        lines: list[str] = []
        for key, item in value.items():
            label = _concept_text(_concept_label(key))
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- **{label}**：")
                lines.extend(_concept_value(item, depth + 1))
            else:
                text = "不适用" if key == "status" and item == "not_applicable" else _concept_text(item)
                lines.append(f"{prefix}- **{label}**：" + text.replace("\n", "\n" + prefix + "    "))
        return lines
    if isinstance(value, list):
        if not value:
            return [prefix + "- 无"]
        lines = []
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- 第 {index} 项：")
                lines.extend(_concept_value(item, depth + 1))
            else:
                lines.append(prefix + "- " + _concept_text(item).replace("\n", "\n" + prefix + "    "))
        return lines
    return [prefix + "- " + _concept_text(value).replace("\n", "\n" + prefix + "    ")]


def render_requirement_markdown(requirement: dict[str, Any], position: dict[str, Any]) -> str:
    """Produce the complete human concept book from the approved canonical objects."""
    asset = requirement["asset"]
    primary = requirement["primary_state"]
    type_names = {"character_master": "角色母版", "location_master": "场景母版",
                  "scene_state": "场景状态", "hero_prop": "关键道具"}
    gate_names = {"asset_selection": "资产选择", "design_requirement": "完整设计需求",
                  "persistence_plan": "落盘与验证计划"}
    lines = [
        "# 《资产概念设计书》", "",
        f"**{_concept_text(asset['name'])} · {_concept_text(requirement['version'])}**", "",
        f"- 资产类型：{type_names.get(asset['asset_type'], _concept_text(asset['asset_type']))}",
        f"- 资产编号：{_concept_text(asset['asset_id'])}",
        f"- 主状态：{_concept_text(primary['label'])}（{_concept_text(primary['state_id'])}）",
        f"- 项目 / 剧本稿次：{_concept_text(requirement['baseline_ref']['project_id'])} / {_concept_text(requirement['baseline_ref']['draft_id'])}",
    ]
    if requirement.get('output_scope'):
        scope = {"pure_environment": "纯环境", "single_asset": "单一资产"}.get(requirement['output_scope'], requirement['output_scope'])
        lines.append(f"- 交付范围：{_concept_text(scope)}")

    def section(title: str, value: Any) -> None:
        lines.extend(["", f"## {title}", "", *_concept_value(value)])

    lines.extend(["", "## 已确认的设计方向", "", _concept_text(primary['design_direction'])])
    section("视觉语言", primary['design_language'])
    section("具体设计元素", primary['concrete_elements'])
    lines.extend(["", "## 主状态与派生状态", "",
                  f"主状态为「{_concept_text(primary['label'])}」（{_concept_text(primary['state_id'])}）；上文定义其完整设计。"])
    if not requirement['derived_states']:
        lines.extend(["", "本版本无派生状态。"])
    for state in requirement['derived_states']:
        lines.extend(["", f"### {_concept_text(state['label'])}（{_concept_text(state['state_id'])}）", "",
                      f"相对 {_concept_text(state['delta_from'])} 的变化；所属资产 {_concept_text(state['asset_id'])}。", "",
                      *_concept_value(state['changes']), "",
                      "来源：" + ("、".join(_concept_text(ref) for ref in state['source_refs']) or "设计决策，无剧本引用")])
    for group, dimensions in requirement['design_dimensions'].items():
        section(_concept_label(group), dimensions)
    section("必须保持的特征与连续性", requirement['invariants'])

    lines.extend(["", "## 导演的完整创作立场", "", _concept_text(position['human_statement']), ""])
    for title, key in [("核心主张", "claim"), ("立场依据", "evidence"), ("审美偏好", "aesthetic_preference"),
                       ("反对意见", "objections"), ("替代方案", "alternative"), ("风险", "risks"),
                       ("改变判断的条件", "change_conditions")]:
        lines.extend([f"### {title}", "", *_concept_value(position[key]), ""])
    confidence = {"high": "高", "medium": "中", "low": "低"}.get(position['confidence'], position['confidence'])
    owner = "用户" if position['decision_owner'] == 'user' else position['decision_owner']
    lines.extend([f"- 判断置信度：{_concept_text(confidence)}", f"- 最终决策权：{_concept_text(owner)}"])
    position_fields = {'schema_version', 'asset_id', 'claim', 'evidence', 'aesthetic_preference', 'objections',
                       'alternative', 'risks', 'confidence', 'change_conditions', 'decision_owner', 'human_statement'}
    position_extra = {key: value for key, value in position.items() if key not in position_fields}
    if position_extra:
        lines.extend(["", "### 补充立场记录", "", *_concept_value(position_extra)])

    lines.extend(["", "## 关键设计决策", ""])
    for decision in requirement['high_impact_decisions']:
        lines.extend([f"### {_concept_text(decision['topic'])}（{_concept_text(decision['id'])}）", ""])
        override = decision['status'] == 'user_override'
        lines.append("- 决策状态：用户覆盖导演原建议" if override else "- 决策状态：已采纳")
        if 'original_recommendation' in decision:
            lines.extend(_concept_value({'original_recommendation': decision['original_recommendation']}))
        lines.append(("- **用户最终选择**：" if override else "- **已采纳方案**：") + _concept_text(decision['chosen_option']))
        lines.extend(_concept_value({'consequence': decision['consequence']}))
        extra = {key: value for key, value in decision.items()
                 if key not in {'id', 'topic', 'status', 'original_recommendation', 'chosen_option', 'consequence'}}
        if extra:
            lines.extend(_concept_value(extra))
        lines.append("")

    section("制作约束", requirement['production_constraints'])
    section("文化边界", requirement['cultural_boundaries'])
    section("明确排除的内容", requirement['exclusions'])
    lines.extend(["", "## 参考图及其控制边界", ""])
    if not requirement['reference_images']:
        lines.append("本版本未采用参考图。")
    for index, reference in enumerate(requirement['reference_images'], 1):
        lines.extend([f"### 参考图 {index}", "",
                      f"- 来源：{'用户提供' if reference['source'] == 'user_provided' else _concept_text(reference['source'])}",
                      f"- 路径：{_concept_text(reference['path'])}", "", "**仅控制以下内容**", "",
                      *_concept_value(reference['controls']), "", "**不得控制以下内容**", "",
                      *_concept_value(reference['must_not_control']), ""])
    lines.extend(["", "## 只读依赖资产", ""])
    if not requirement['dependency_assets']:
        lines.append("本版本无依赖资产。")
    for dependency in requirement['dependency_assets']:
        lines.extend([f"- {_concept_text(dependency['ref_asset_id'])} · {type_names.get(dependency['asset_type'], _concept_text(dependency['asset_type']))} · {_concept_text(dependency['version'])}（只读引用）",
                      "    - 保留母版设计；文件路径与内容摘要见附录。"])
    lines.extend(["", "## 验收标准", ""])
    for criterion in requirement['acceptance_criteria']:
        lines.extend([f"### {_concept_text(criterion['id'])}", "", _concept_text(criterion['criterion']), "",
                      f"验证方法：{_concept_text(criterion['method'])}", ""])
    lines.extend(["", "## 用户确认记录", ""])
    for confirmation in requirement['confirmations']:
        status = '已确认' if confirmation['confirmed'] else '未确认'
        confirmed_by = '用户' if confirmation.get('confirmed_by') == 'user' else confirmation.get('confirmed_by', '未提供')
        lines.extend([f"### {gate_names.get(confirmation['gate'], _concept_text(confirmation['gate']))}", "",
                      f"- 状态：{status}", f"- 确认人：{_concept_text(confirmed_by)}",
                      f"- 确认时间：{_concept_text(confirmation['confirmed_at'])}",
                      f"- 用户消息引用：{_concept_text(confirmation.get('message_ref', '未提供'))}", ""])
    section("待解决问题", requirement['open_questions'])

    lines.extend(["", "<details>", "<summary>证据、版本与来源记录（展开查看）</summary>", "",
                  "### 证据及性质", ""])
    kinds = {"fact": "剧本事实", "inference": "推断", "design_decision": "设计决策", "preference": "审美偏好", "unknown": "未知"}
    for item in requirement['evidence']:
        lines.append(f"- **{kinds.get(item['kind'], _concept_text(item['kind']))}**：{_concept_text(item['statement'])}")
        lines.append("    - 来源引用：" + ("、".join(_concept_text(ref) for ref in item['source_refs']) or "无剧本引用"))
        extra = {key: value for key, value in item.items() if key not in {'kind', 'statement', 'source_refs'}}
        if extra:
            lines.extend(_concept_value(extra, 1))
    lines.extend(["", "### 版本与基线来源", "", *_concept_value({
        'schema_version': requirement['schema_version'], 'contract_revision': requirement.get('contract_revision'),
        'version': requirement['version'], **requirement['baseline_ref']}), "",
        "### 导演立场与需求绑定", "", *_concept_value({
        'schema_version': position['schema_version'], 'asset_id': position['asset_id'],
        'creative_position_hash': requirement.get('creative_position_hash'), **requirement.get('integrity', {})}), ""])
    for confirmation in requirement['confirmations']:
        lines.extend([f"- {gate_names.get(confirmation['gate'], _concept_text(confirmation['gate']))} · 内容摘要：{_concept_text(confirmation.get('content_hash', '未提供'))}"])
    if requirement['dependency_assets']:
        lines.extend(["", "### 依赖资产内容摘要", ""])
        for dependency in requirement['dependency_assets']:
            lines.extend(_concept_value({key: dependency[key] for key in ('ref_asset_id', 'version', 'requirement_path', 'requirement_hash')}))
    if requirement['reference_images']:
        lines.extend(["", "### 参考图内容摘要", ""])
        for reference in requirement['reference_images']:
            lines.extend(_concept_value({'path': reference['path'], 'sha256': reference['sha256']}))
    lines.extend(["", "### 已确认的交付与校验计划", "", *_concept_value(requirement.get('persistence_plan', {})), "", "</details>"])
    return "\n".join(lines).rstrip() + "\n"


def render_decision_log(requirement: dict[str, Any]) -> str:
    lines = ["# Decision log", "", "## High-impact decisions", ""]
    for decision in requirement["high_impact_decisions"]:
        lines.append(f"- `{decision.get('id', 'decision')}` **{decision.get('topic', '')}**: {decision['chosen_option']} ({decision['status']}) — {decision.get('consequence', '')}")
    lines.extend(["", "## Confirmations", ""])
    for confirmation in requirement["confirmations"]:
        lines.append(f"- `{confirmation['gate']}` confirmed at {confirmation['confirmed_at']}")
    return "\n".join(lines) + "\n"


def check_existing_book(path: Path, content: str) -> bool:
    """An approved version is immutable, including the public reading copy."""
    if path.is_symlink():
        raise ValueError(f'Design book destination must not be a symlink: {path}')
    if path.exists():
        if not path.is_file() or path.read_bytes() != content.encode('utf-8'):
            raise ValueError(f'Design book already exists with different content: {path}')
        return True
    return False


def publish_design_book(path: Path, content: str) -> None:
    """Publish complete bytes without replacing a concurrent or existing file."""
    if check_existing_book(path, content):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.design-book-', dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_text(content, encoding='utf-8')
        # The temporary file and destination share a filesystem. link is atomic
        # and fails if another writer already published this immutable version.
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not check_existing_book(path, content):
                raise FileNotFoundError(f'Design book disappeared during publication: {path}')
    finally:
        temporary.unlink(missing_ok=True)


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
    if output_root.resolve() != Path(requirement['persistence_plan']['output_root']).resolve():
        raise ValueError('Output destination differs from the approved persistence plan')
    project_id = safe_segment(requirement["baseline_ref"]["project_id"])
    draft_id = safe_segment(requirement["baseline_ref"]["draft_id"])
    asset_id = safe_segment(requirement["asset"]["asset_id"])
    version = safe_segment(requirement["version"])
    project_dir = output_root.resolve() / project_id / draft_id
    version_dir = project_dir / "assets" / asset_id / version
    contents = {
        'context-snapshot.json': json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
        'requirement.json': json.dumps(requirement, ensure_ascii=False, indent=2) + '\n',
        'creative-position.json': json.dumps(position, ensure_ascii=False, indent=2) + '\n',
        'asset-catalog.json': json.dumps(catalog, ensure_ascii=False, indent=2) + '\n',
        'requirement.md': render_requirement_markdown(requirement, position),
        'decision-log.md': render_decision_log(requirement),
    }
    book_path = (Path(requirement['persistence_plan']['design_book_path'])
                 if 'design_book_path' in requirement['persistence_plan']
                 else version_dir / 'requirement.md')
    if 'design_book_path' in requirement['persistence_plan']:
        check_existing_book(book_path, contents['requirement.md'])
    if version_dir.exists():
        if set(p.name for p in version_dir.iterdir()) != set(contents) or any((version_dir / name).read_text(encoding='utf-8') != body for name, body in contents.items()):
            raise ValueError(f'Asset version already exists with different or incomplete content: {version_dir}')
    else:
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f'.{version}-', dir=version_dir.parent))
        try:
            for name, body in contents.items():
                (temporary / name).write_text(body, encoding='utf-8')
            # A complete nonempty directory is renamed as one unit. A concurrent
            # writer cannot replace an already committed nonempty version.
            os.rename(temporary, version_dir)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if 'design_book_path' in requirement['persistence_plan']:
        # Commit verified machine data first. If public storage fails, retry can
        # reuse this complete package; no partial public book has been exposed.
        publish_design_book(book_path, contents['requirement.md'])
    outputs = {
        "context_snapshot": version_dir / "context-snapshot.json",
        "requirement_json": version_dir / "requirement.json",
        "requirement_markdown": version_dir / "requirement.md",
        "creative_position": version_dir / "creative-position.json",
        "decision_log": version_dir / "decision-log.md",
        "asset_catalog": version_dir / 'asset-catalog.json',
    }
    return {
        "status": "succeeded",
        "asset_id": asset_id,
        "version": version,
        "deliverables": {"asset_concept_book": str(book_path)},
        "machine_handoff": str(outputs['requirement_json']),
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
    snapshot.add_argument('--max-scenes', type=int, default=40)
    snapshot.add_argument('--max-beats', type=int, default=80)
    snapshot.add_argument('--max-findings', type=int, default=80)
    snapshot.add_argument('--max-context-bytes', type=int, default=200000)
    validate = commands.add_parser("validate-requirement")
    validate.add_argument("--requirement", type=Path, required=True)
    validate.add_argument("--snapshot", type=Path, required=True)
    validate.add_argument("--position", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    persist = commands.add_parser("materialize")
    persist.add_argument("--catalog", type=Path, required=True)
    persist.add_argument("--snapshot", type=Path, required=True)
    persist.add_argument("--requirement", type=Path, required=True)
    persist.add_argument("--position", type=Path, required=True)
    persist.add_argument("--output-root", type=Path, required=True)
    persist.add_argument("--output", type=Path)
    persist.add_argument("--details", action="store_true", help="Include internal package paths for automation")
    digest = commands.add_parser('confirmation-digest')
    digest.add_argument('--requirement', type=Path, required=True)
    digest.add_argument('--gate', choices=sorted(CONFIRMATION_GATES), required=True)
    seal = commands.add_parser('seal')
    for field in ('requirement', 'snapshot', 'position', 'output'):
        seal.add_argument('--' + field, type=Path, required=True)
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
            payload = build_snapshot(load_json(args.breakdown), load_json(args.catalog), args.asset_id,
                                     breakdown_path=args.breakdown, max_scenes=args.max_scenes,
                                     max_beats=args.max_beats, max_findings=args.max_findings,
                                     max_context_bytes=args.max_context_bytes)
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
            if not args.details:
                payload = {key: payload[key] for key in ('status', 'asset_id', 'version', 'deliverables', 'validation')}
            write_json(payload, args.output)
        elif args.command == 'confirmation-digest':
            write_json({'gate': args.gate, 'content_hash': confirmation_hash(load_json(args.requirement), args.gate),
                        'note': 'Digest only; this command does not confirm or authorize anything.'})
        elif args.command == 'seal':
            payload = seal_requirement(load_json(args.requirement), load_json(args.snapshot), load_json(args.position))
            write_json(payload, args.output)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        write_json({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
