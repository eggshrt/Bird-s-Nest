#!/usr/bin/env python3
"""Validate AI screenplay breakdown invariants without third-party packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TOP_LEVEL_REQUIRED = {
    "schema_version",
    "project",
    "source_manifest",
    "coverage",
    "global_analysis",
    "entities",
    "scenes",
    "beats",
    "ai_feasibility",
    "role_reports",
    "issues",
    "cross_role_decisions",
    "theory_trace",
    "handoff",
}
AI_BASELINE_REQUIRED = {
    "asset_locks",
    "continuity_requirements",
    "complexity_flags",
    "reference_requirements",
    "duration_pressure",
    "audio_dependencies",
    "risks",
    "fallbacks",
    "blockers",
}
FINDING_REQUIRED = {
    "id",
    "role_id",
    "source_refs",
    "scene_ids",
    "beat_ids",
    "certainty",
    "confidence",
    "severity",
    "observation",
    "impact",
    "recommendation",
    "theory_refs",
}
ROLE_REPORT_REQUIRED = {
    "role_id",
    "display_name",
    "status",
    "contract",
    "findings",
    "deliverables",
    "dependencies",
    "blockers",
}
FORBIDDEN_STORYBOARD_KEYS = {"prompt", "generation_prompt", "negative_prompt", "provider_prompt"}


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def load_json(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Breakdown root must be a JSON object")
    return data


def require_keys(result: ValidationResult, value: Any, keys: set[str], path: str) -> None:
    if not isinstance(value, dict):
        result.error(f"{path} must be an object")
        return
    missing = sorted(keys - set(value))
    if missing:
        result.error(f"{path} missing keys: {', '.join(missing)}")


def string_set(result: ValidationResult, value: Any, path: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        result.error(f"{path} must be an array of strings")
        return set()
    if len(value) != len(set(value)):
        result.error(f"{path} contains duplicate values")
    return set(value)


def validate_manifest(result: ValidationResult, manifest: Any) -> None:
    required = {"source_id", "draft_id", "format", "sha256", "extraction_quality", "warnings"}
    require_keys(result, manifest, required, "source_manifest")
    if not isinstance(manifest, dict):
        return
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("sha256", ""))):
        result.error("source_manifest.sha256 must be a lowercase SHA-256 digest")
    if manifest.get("extraction_quality") not in {"good", "degraded", "failed"}:
        result.error("source_manifest.extraction_quality has an invalid value")
    if not isinstance(manifest.get("warnings"), list):
        result.error("source_manifest.warnings must be an array")


def validate_coverage(
    result: ValidationResult, coverage: Any
) -> tuple[set[str], set[str], set[str], str | None]:
    required = {
        "status",
        "requested_scene_ids",
        "completed_scene_ids",
        "pending_scene_ids",
        "requested_role_ids",
        "completed_role_ids",
        "pending_role_ids",
        "ai_baseline_completed",
        "cross_role_synthesis_completed",
        "current_batch",
        "continuation_anchor",
    }
    require_keys(result, coverage, required, "coverage")
    if not isinstance(coverage, dict):
        return set(), set(), set(), None
    requested_scenes = string_set(result, coverage.get("requested_scene_ids"), "coverage.requested_scene_ids")
    completed_scenes = string_set(result, coverage.get("completed_scene_ids"), "coverage.completed_scene_ids")
    pending_scenes = string_set(result, coverage.get("pending_scene_ids"), "coverage.pending_scene_ids")
    requested_roles = string_set(result, coverage.get("requested_role_ids"), "coverage.requested_role_ids")
    completed_roles = string_set(result, coverage.get("completed_role_ids"), "coverage.completed_role_ids")
    pending_roles = string_set(result, coverage.get("pending_role_ids"), "coverage.pending_role_ids")

    if completed_scenes & pending_scenes:
        result.error("coverage scene completion and pending sets overlap")
    if completed_roles & pending_roles:
        result.error("coverage role completion and pending sets overlap")
    if requested_scenes != completed_scenes | pending_scenes:
        result.error("coverage requested scenes must equal completed plus pending scenes")
    if requested_roles != completed_roles | pending_roles:
        result.error("coverage requested roles must equal completed plus pending roles")

    status = coverage.get("status")
    if status not in {"blocked", "partial", "completed"}:
        result.error("coverage.status has an invalid value")
    if status == "completed":
        if pending_scenes or pending_roles:
            result.error("completed coverage cannot retain pending scenes or roles")
        if coverage.get("ai_baseline_completed") is not True:
            result.error("completed coverage requires ai_baseline_completed=true")
        if coverage.get("cross_role_synthesis_completed") is not True:
            result.error("completed coverage requires cross_role_synthesis_completed=true")
        if coverage.get("continuation_anchor") is not None:
            result.error("completed coverage cannot retain a continuation anchor")
    elif pending_scenes and not coverage.get("continuation_anchor"):
        result.warn("pending scenes exist without a continuation anchor")
    return requested_scenes, requested_roles, completed_roles, status


def validate_traceable_items(
    result: ValidationResult,
    items: Any,
    path: str,
    id_pattern: str,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    if not isinstance(items, list):
        result.error(f"{path} must be an array")
        return set(), {}
    ids: set[str] = set()
    records: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            result.error(f"{item_path} must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not re.fullmatch(id_pattern, item_id):
            result.error(f"{item_path}.id is invalid")
            continue
        if item_id in ids:
            result.error(f"duplicate ID: {item_id}")
        ids.add(item_id)
        records[item_id] = item
        refs = item.get("source_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
            result.error(f"{item_path}.source_refs must contain at least one reference")
    return ids, records


def find_forbidden_keys(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key.casefold() in FORBIDDEN_STORYBOARD_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_keys(child, f"{path}[{index}]"))
    return found


def validate_finding(
    result: ValidationResult,
    finding: Any,
    path: str,
    scene_ids: set[str],
    beat_ids: set[str],
    theory_ids: set[str],
) -> str | None:
    require_keys(result, finding, FINDING_REQUIRED, path)
    if not isinstance(finding, dict):
        return None
    finding_id = finding.get("id")
    if not isinstance(finding_id, str) or not re.fullmatch(r"fnd-[0-9]{3,}", finding_id):
        result.error(f"{path}.id is invalid")
        finding_id = None
    certainty = finding.get("certainty")
    if certainty not in {"explicit", "inferred", "unknown"}:
        result.error(f"{path}.certainty is invalid")
    if finding.get("confidence") not in {"high", "medium", "low"}:
        result.error(f"{path}.confidence is invalid")
    if finding.get("severity") not in {"blocker", "high", "medium", "low"}:
        result.error(f"{path}.severity is invalid")
    refs = finding.get("source_refs")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        result.error(f"{path}.source_refs must be an array of strings")
        refs = []
    related_scenes = string_set(result, finding.get("scene_ids"), f"{path}.scene_ids")
    related_beats = string_set(result, finding.get("beat_ids"), f"{path}.beat_ids")
    if related_scenes - scene_ids:
        result.error(f"{path}.scene_ids contains unknown IDs: {sorted(related_scenes - scene_ids)}")
    if related_beats - beat_ids:
        result.error(f"{path}.beat_ids contains unknown IDs: {sorted(related_beats - beat_ids)}")
    if certainty in {"explicit", "inferred"} and not refs and not related_scenes and not related_beats:
        result.error(f"{path} requires evidence for certainty={certainty}")
    if certainty == "unknown" and not refs and not related_scenes and not related_beats:
        result.error(f"{path} unknown finding must identify an affected scene, beat, or source dependency")
    for field in ("observation", "impact", "recommendation", "role_id"):
        if not isinstance(finding.get(field), str) or not finding[field].strip():
            result.error(f"{path}.{field} must be a non-empty string")
    finding_theories = string_set(result, finding.get("theory_refs"), f"{path}.theory_refs")
    missing_theories = finding_theories - theory_ids
    if missing_theories:
        result.error(f"{path}.theory_refs not present in theory_trace: {sorted(missing_theories)}")
    return finding_id


def validate_breakdown(data: dict[str, Any], markdown: str | None = None) -> ValidationResult:
    result = ValidationResult()
    require_keys(result, data, TOP_LEVEL_REQUIRED, "root")
    if data.get("schema_version") != "1.0.0":
        result.error("schema_version must be 1.0.0")
    project = data.get("project")
    require_keys(result, project, {"id", "format", "production_model"}, "project")
    if isinstance(project, dict) and project.get("production_model") != "fully_ai_photoreal_live_action":
        result.error("project.production_model must be fully_ai_photoreal_live_action")
    manifest = data.get("source_manifest")
    validate_manifest(result, manifest)
    requested_scene_ids, requested_role_ids, completed_role_ids, coverage_status = validate_coverage(
        result, data.get("coverage")
    )
    if coverage_status == "completed" and isinstance(manifest, dict) and manifest.get("extraction_quality") == "failed":
        result.error("completed coverage cannot use a failed source extraction")

    global_analysis = data.get("global_analysis")
    require_keys(
        result,
        global_analysis,
        {
            "story_contract",
            "narrative_form",
            "causal_spine",
            "character_system",
            "information_design",
            "theme_values",
            "setup_payoff",
            "world_rules",
            "rhythm",
            "continuity",
        },
        "global_analysis",
    )

    scene_ids, scenes = validate_traceable_items(result, data.get("scenes"), "scenes", r"scn-[0-9]{3,}")
    beat_ids, beats = validate_traceable_items(result, data.get("beats"), "beats", r"bea-[0-9]{3,}")
    if requested_scene_ids - scene_ids:
        result.error(f"coverage references scenes absent from scenes: {sorted(requested_scene_ids - scene_ids)}")
    for scene_id, scene in scenes.items():
        for key in ("heading", "certainty", "entry_state", "exit_state", "summary"):
            if key not in scene:
                result.error(f"scene {scene_id} missing key: {key}")
        if scene.get("certainty") not in {"explicit", "inferred"}:
            result.error(f"scene {scene_id} has invalid certainty")
        if not isinstance(scene.get("entry_state"), dict) or not isinstance(scene.get("exit_state"), dict):
            result.error(f"scene {scene_id} entry_state and exit_state must be objects")
    for beat_id, beat in beats.items():
        if beat.get("scene_id") not in scenes:
            result.error(f"beat {beat_id} references unknown scene_id {beat.get('scene_id')}")
        for key in ("change", "entry_state", "exit_state"):
            if key not in beat:
                result.error(f"beat {beat_id} missing key: {key}")
        if not isinstance(beat.get("change"), str) or not beat.get("change", "").strip():
            result.error(f"beat {beat_id}.change must be a non-empty string")
        if not isinstance(beat.get("entry_state"), dict) or not isinstance(beat.get("exit_state"), dict):
            result.error(f"beat {beat_id} entry_state and exit_state must be objects")

    entities = data.get("entities")
    require_keys(result, entities, {"characters", "locations", "props", "effects"}, "entities")
    if isinstance(entities, dict):
        entity_ids: set[str] = set()
        for key in ("characters", "locations", "props", "effects"):
            items = entities.get(key)
            if not isinstance(items, list):
                result.error(f"entities.{key} must be an array")
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    result.error(f"entities.{key}[{index}] requires an ID")
                    continue
                if item["id"] in entity_ids:
                    result.error(f"duplicate entity ID: {item['id']}")
                entity_ids.add(item["id"])
                if item.get("certainty") in {"explicit", "inferred"} and not item.get("source_refs"):
                    result.error(f"entities.{key}[{index}] requires source_refs")

    ai_feasibility = data.get("ai_feasibility")
    require_keys(result, ai_feasibility, AI_BASELINE_REQUIRED, "ai_feasibility")
    if isinstance(ai_feasibility, dict):
        for key in AI_BASELINE_REQUIRED:
            if not isinstance(ai_feasibility.get(key), list):
                result.error(f"ai_feasibility.{key} must be an array")

    theory_trace = data.get("theory_trace")
    theory_ids: set[str] = set()
    if not isinstance(theory_trace, list):
        result.error("theory_trace must be an array")
    else:
        for index, trace in enumerate(theory_trace):
            if not isinstance(trace, dict) or not isinstance(trace.get("theory_id"), str):
                result.error(f"theory_trace[{index}] requires theory_id")
                continue
            theory_id = trace["theory_id"]
            if theory_id in theory_ids:
                result.error(f"duplicate theory_trace ID: {theory_id}")
            theory_ids.add(theory_id)

    finding_registry: dict[str, dict[str, Any]] = {}
    issues = data.get("issues")
    if not isinstance(issues, list):
        result.error("issues must be an array")
        issues = []
    for index, finding in enumerate(issues):
        finding_id = validate_finding(
            result, finding, f"issues[{index}]", scene_ids, beat_ids, theory_ids
        )
        if finding_id:
            finding_registry[finding_id] = finding

    reports = data.get("role_reports")
    report_roles: set[str] = set()
    if not isinstance(reports, list):
        result.error("role_reports must be an array")
        reports = []
    for index, report in enumerate(reports):
        path = f"role_reports[{index}]"
        require_keys(result, report, ROLE_REPORT_REQUIRED, path)
        if not isinstance(report, dict):
            continue
        role_id = report.get("role_id")
        if not isinstance(role_id, str):
            result.error(f"{path}.role_id must be a string")
            continue
        if role_id in report_roles:
            result.error(f"duplicate role report: {role_id}")
        report_roles.add(role_id)
        if report.get("status") not in {"blocked", "partial", "completed"}:
            result.error(f"{path}.status is invalid")
        if role_id in completed_role_ids and report.get("status") != "completed":
            result.error(f"{path}.status must be completed because coverage marks the role completed")
        if role_id.startswith("role-"):
            contract = report.get("contract")
            if not isinstance(contract, dict) or contract.get("confirmed") is not True:
                result.error(f"{path} custom role requires a confirmed contract")
        findings = report.get("findings")
        if not isinstance(findings, list):
            result.error(f"{path}.findings must be an array")
            findings = []
        for finding_index, finding in enumerate(findings):
            finding_path = f"{path}.findings[{finding_index}]"
            finding_id = validate_finding(
                result, finding, finding_path, scene_ids, beat_ids, theory_ids
            )
            if finding_id:
                previous = finding_registry.get(finding_id)
                if previous is not None and previous != finding:
                    result.error(f"finding {finding_id} has conflicting definitions")
                finding_registry[finding_id] = finding
        if role_id == "storyboard":
            forbidden = find_forbidden_keys(report)
            if forbidden:
                result.error(f"storyboard report contains forbidden prompt fields: {forbidden}")

    missing_reports = requested_role_ids - report_roles
    if missing_reports:
        result.error(f"requested roles missing reports: {sorted(missing_reports)}")

    decisions = data.get("cross_role_decisions")
    if not isinstance(decisions, list):
        result.error("cross_role_decisions must be an array")
    else:
        decision_ids: set[str] = set()
        for index, decision in enumerate(decisions):
            path = f"cross_role_decisions[{index}]"
            if not isinstance(decision, dict):
                result.error(f"{path} must be an object")
                continue
            decision_id = decision.get("id")
            if not isinstance(decision_id, str) or not re.fullmatch(r"dec-[0-9]{3,}", decision_id):
                result.error(f"{path}.id is invalid")
            elif decision_id in decision_ids:
                result.error(f"duplicate decision ID: {decision_id}")
            else:
                decision_ids.add(decision_id)
            for key in ("topic", "affected_role_ids", "source_refs", "conflict", "options", "recommended_option", "decision_owner", "required_by", "status"):
                if key not in decision:
                    result.error(f"{path} missing key: {key}")

    handoff = data.get("handoff")
    require_keys(result, handoff, {"artifacts", "ready_for", "blocked_by"}, "handoff")
    if isinstance(handoff, dict):
        for key in ("artifacts", "ready_for", "blocked_by"):
            if not isinstance(handoff.get(key), list) or any(
                not isinstance(item, str) for item in handoff.get(key, [])
            ):
                result.error(f"handoff.{key} must be an array of strings")

    if markdown is not None:
        project_id = str(project.get("id")) if isinstance(project, dict) else ""
        if project_id and project_id not in markdown:
            result.error("Markdown does not contain the project ID")
        for scene_id in sorted(requested_scene_ids):
            if scene_id not in markdown:
                result.error(f"Markdown does not mention requested scene {scene_id}")
        for finding_id in sorted(finding_registry):
            if finding_id not in markdown:
                result.error(f"Markdown does not mention finding {finding_id}")
        for report in reports:
            display_name = report.get("display_name") if isinstance(report, dict) else None
            if display_name and display_name not in markdown:
                result.error(f"Markdown does not mention role {display_name}")

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("breakdown", help="breakdown.json path")
    parser.add_argument("--markdown", help="Optional breakdown.md consistency check")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = load_json(args.breakdown)
        markdown = Path(args.markdown).read_text(encoding="utf-8") if args.markdown else None
        result = validate_breakdown(data, markdown)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print("Breakdown is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
