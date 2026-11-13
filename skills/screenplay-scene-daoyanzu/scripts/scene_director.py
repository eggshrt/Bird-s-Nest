#!/usr/bin/env python3
"""Validate, seal, and materialize SceneDirectionPackageV1 without runtime deps."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from xml.sax.saxutils import escape
import zipfile


SCHEMA_REQUIREMENT = "SceneDirectionRequirementV1"
SCHEMA_PACKAGE = "SceneDirectionPackageV1"
PERMANENT_ROLES = {
    "scene-zongdaoyan", "scene-biaoyan-diaodu-daoyan",
    "scene-sheying-fenjing-daoyan", "scene-lianxuxing-zhixing-daoyan",
}
ALLOWED_ROLES = PERMANENT_ROLES | {
    "scene-dongzuo-daoyan", "scene-taici-daoyan", "scene-dengguang-daoyan",
    "scene-tiaose-daoyan", "scene-shengyin-daoyan", "scene-texiao-daoyan",
    "scene-chuangyi-daoyan",
}
FORBIDDEN_KEYS = {
    "prompt", "negative_prompt", "model_parameters", "image_generation",
    "budget", "schedule", "call_sheet", "asset_redesign",
}
SHOT_FIELDS = [
    "shot_id", "scene_id", "production_scene_code", "beat_ids", "evidence_refs",
    "dramatic_purpose", "information_change", "subject_action", "reaction",
    "performance_target", "framing", "angle", "camera_position", "lens_tendency",
    "movement", "blocking", "axis", "eyeline", "spatial_layers", "duration_seconds",
    "first_state", "last_state", "sound", "light_color", "transition", "continuity",
    "dependencies", "risk", "fallback", "acceptance_check",
]
SHOT_SEGMENT_FIELDS = [
    "segment_id", "beat_ids", "evidence_refs", "framing", "angle",
    "camera_position", "movement", "subject_action", "performance_target",
    "dialogue", "sound", "last_state",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def package_digest(package: dict[str, Any]) -> str:
    value = deepcopy(package)
    value["integrity"] = {"canonical_json_sha256": None}
    return hash_json(value)


def _quadrants(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != "CollaborationContextV1":
        errors.append("collaboration_context.schema_version must be CollaborationContextV1")
    for key in ("shared_known", "user_context_gaps", "agent_added_context", "joint_unknown_hypotheses"):
        if not isinstance(value.get(key), list):
            errors.append(f"collaboration_context.{key} must be a list")
    return errors


def validate_requirement(value: dict[str, Any], breakdown: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_REQUIREMENT:
        errors.append(f"schema_version must be {SCHEMA_REQUIREMENT}")
    scenes = value.get("scene_ids")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 2:
        errors.append("scene_ids must contain 1 or 2 scenes")
        scenes = []
    if len(scenes) != len(set(scenes)):
        errors.append("scene_ids must be unique")
    mapping = value.get("production_scene_map")
    if not isinstance(mapping, dict) or set(mapping) != set(scenes):
        errors.append("production_scene_map must map every selected scene exactly once")
        mapping = {}
    codes = list(mapping.values())
    if len(codes) != len(set(codes)) or any(not re.fullmatch(r"[A-Z][A-Z0-9]*S\d{3}", str(code)) for code in codes):
        errors.append("production scene codes must be unique and match E001S001 style")
    numbering = value.get("shot_numbering", {})
    if numbering.get("pattern") != "{production_scene_code}C{sequence:03d}" or numbering.get("reset_per_scene") is not True:
        errors.append("shot numbering must reset per scene and use the canonical pattern")
    roles = value.get("active_roles")
    if not isinstance(roles, list) or not PERMANENT_ROLES.issubset(set(roles)):
        errors.append("all four permanent roles are required")
    elif not set(roles).issubset(ALLOWED_ROLES):
        errors.append("active_roles contains an unknown role")
    confirmation = value.get("initial_confirmation", {})
    if confirmation.get("status") != "confirmed" or not confirmation.get("confirmed_at"):
        errors.append("first Grill must be confirmed before DAG creation")
    errors.extend(_quadrants(value.get("collaboration_context", {})))
    if breakdown:
        if breakdown.get("schema_version") != "1.0.0":
            errors.append("breakdown must be screenplay_breakdown_v1 (schema 1.0.0)")
        known = {item.get("id") for item in breakdown.get("scenes", [])}
        missing = sorted(set(scenes) - known)
        if missing:
            errors.append("unknown scene IDs: " + ", ".join(missing))
        if value.get("project_id") != breakdown.get("project", {}).get("id"):
            errors.append("project_id does not match breakdown")
        if value.get("screenplay_hash") != breakdown.get("source_manifest", {}).get("sha256"):
            errors.append("screenplay_hash does not match breakdown")
        if value.get("breakdown_hash") != hash_json(breakdown):
            errors.append("breakdown_hash does not match canonical breakdown")
    return sorted(set(errors))


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                errors.append(f"forbidden field {path}.{key}")
            errors.extend(_walk_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return errors


def validate_package(value: dict[str, Any], breakdown: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_PACKAGE:
        errors.append(f"schema_version must be {SCHEMA_PACKAGE}")
    requirement = value.get("requirement", {})
    errors.extend(validate_requirement(requirement, breakdown))
    selected = requirement.get("scene_ids", [])
    scenes = value.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(selected):
        errors.append("package scenes must match selected scene count")
        scenes = []
    if [item.get("scene_id") for item in scenes] != selected:
        errors.append("package scenes must preserve requirement scene order")
    breakdown_beats = {item.get("id"): item for item in (breakdown or {}).get("beats", [])}
    all_shots: set[str] = set()
    for scene in scenes:
        scene_id = scene.get("scene_id")
        code = scene.get("production_scene_code")
        if requirement.get("production_scene_map", {}).get(scene_id) != code:
            errors.append(f"{scene_id}: production scene code mismatch")
        shots = scene.get("shots")
        if not isinstance(shots, list) or not shots:
            errors.append(f"{scene_id}: shots must be non-empty")
            continue
        expected = [f"{code}C{index:03d}" for index in range(1, len(shots) + 1)]
        actual = [shot.get("shot_id") for shot in shots]
        if actual != expected:
            errors.append(f"{scene_id}: shot numbers must start at 001 and be contiguous")
        for shot in shots:
            shot_id = str(shot.get("shot_id", ""))
            if shot_id in all_shots:
                errors.append(f"duplicate shot ID: {shot_id}")
            all_shots.add(shot_id)
            missing = [field for field in SHOT_FIELDS if field not in shot]
            if missing:
                errors.append(f"{shot_id}: missing shot fields: {', '.join(missing)}")
            if shot.get("scene_id") != scene_id or shot.get("production_scene_code") != code:
                errors.append(f"{shot_id}: scene linkage mismatch")
            beat_ids = shot.get("beat_ids")
            refs = shot.get("evidence_refs")
            if not isinstance(beat_ids, list) or not beat_ids or not isinstance(refs, list) or not refs:
                errors.append(f"{shot_id}: beat_ids and evidence_refs are required")
            if breakdown:
                for beat_id in beat_ids or []:
                    beat = breakdown_beats.get(beat_id)
                    if not beat or beat.get("scene_id") != scene_id:
                        errors.append(f"{shot_id}: invalid beat reference {beat_id}")
            segments = shot.get("shot_segments")
            if segments is not None:
                if not isinstance(segments, list) or not segments:
                    errors.append(f"{shot_id}: shot_segments must be a non-empty list when present")
                    segments = []
                expected_segments = [f"{shot_id}-{index}" for index in range(1, len(segments) + 1)]
                actual_segments = [segment.get("segment_id") if isinstance(segment, dict) else None for segment in segments]
                if actual_segments != expected_segments:
                    errors.append(f"{shot_id}: subshots must start at -1 and be contiguous")
                for segment in segments:
                    if not isinstance(segment, dict):
                        errors.append(f"{shot_id}: every shot segment must be an object")
                        continue
                    segment_id = str(segment.get("segment_id", ""))
                    if segment_id in all_shots:
                        errors.append(f"duplicate shot ID: {segment_id}")
                    all_shots.add(segment_id)
                    missing = [field for field in SHOT_SEGMENT_FIELDS if field not in segment]
                    if missing:
                        errors.append(f"{segment_id or shot_id}: missing segment fields: {', '.join(missing)}")
                    segment_beats = segment.get("beat_ids")
                    segment_refs = segment.get("evidence_refs")
                    if not isinstance(segment_beats, list) or not segment_beats or not isinstance(segment_refs, list) or not segment_refs:
                        errors.append(f"{segment_id or shot_id}: beat_ids and evidence_refs are required")
                    for field in ("segment_id", "framing", "angle", "camera_position", "movement", "subject_action", "performance_target", "last_state"):
                        if not isinstance(segment.get(field), str) or not segment[field].strip():
                            errors.append(f"{segment_id or shot_id}: {field} must be non-empty")
                    if breakdown:
                        for beat_id in segment_beats or []:
                            beat = breakdown_beats.get(beat_id)
                            if not beat or beat.get("scene_id") != scene_id:
                                errors.append(f"{segment_id or shot_id}: invalid beat reference {beat_id}")
        target = requirement.get("duration_targets", {}).get(scene_id)
        if isinstance(target, dict) and isinstance(target.get("min_seconds"), (int, float)) and isinstance(target.get("max_seconds"), (int, float)):
            actual_duration = sum(shot.get("duration_seconds", 0) for shot in shots if isinstance(shot.get("duration_seconds"), (int, float)))
            if not target["min_seconds"] <= actual_duration <= target["max_seconds"]:
                errors.append(f"{scene_id}: total duration {actual_duration}s is outside {target['min_seconds']}-{target['max_seconds']}s")
    decisions = value.get("decision_log")
    if not isinstance(decisions, list):
        errors.append("decision_log must be a list")
        decisions = []
    for decision in decisions:
        if decision.get("rebuttal_count", 0) not in (0, 1):
            errors.append(f"{decision.get('decision_id')}: at most one rebuttal is allowed")
        if value.get("status") == "sealed" and decision.get("status") != "user_decided":
            errors.append(f"{decision.get('decision_id')}: sealed package has an unresolved decision")
    final = value.get("final_confirmation", {})
    if value.get("status") == "sealed" and (final.get("status") != "confirmed" or not final.get("confirmed_at")):
        errors.append("sealed package requires second-Grill final confirmation")
    if value.get("status") == "sealed":
        recorded = value.get("integrity", {}).get("canonical_json_sha256")
        if recorded != package_digest(value):
            errors.append("canonical_json_sha256 does not match package")
    errors.extend(_walk_forbidden(value))
    return sorted(set(errors))


def seal_package(value: dict[str, Any]) -> dict[str, Any]:
    sealed = deepcopy(value)
    sealed["status"] = "sealed"
    sealed.setdefault("integrity", {})["canonical_json_sha256"] = None
    sealed["integrity"]["canonical_json_sha256"] = package_digest(sealed)
    return sealed


def _zip_write(archive: zipfile.ZipFile, name: str, data: str | bytes) -> None:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)


def _doc_p(text: Any, style: str | None = None) -> str:
    value = escape(_string(text))
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p>'


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(_string(item) for item in value)
    if isinstance(value, dict):
        return "；".join(f"{key}: {_string(child)}" for key, child in value.items())
    return str(value)


def render_docx(package: dict[str, Any], output: Path) -> None:
    template_path = Path(__file__).resolve().parents[1] / "assets" / "docx-template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    margins = int(template.get("page", {}).get("margins_twips", 1440))
    digest = package["integrity"]["canonical_json_sha256"]
    body = [_doc_p("导演执行包", "Title"), _doc_p(f"包 ID：{package.get('package_id')}"), _doc_p(f"版本：{package.get('version')}"), _doc_p(f"规范 JSON SHA-256：{digest}")]
    chief = package.get("chief_direction", {})
    body += [_doc_p("总导演决策摘要", "Heading1")]
    for key, value in chief.items():
        body.append(_doc_p(f"{key}：{_string(value)}"))
    for scene in package.get("scenes", []):
        body += [_doc_p(f"{scene['production_scene_code']} · {scene.get('title', '')}", "Heading1"), _doc_p(f"内部 ID：{scene['scene_id']}"), _doc_p(f"戏剧功能：{_string(scene.get('dramatic_function'))}"), _doc_p("节拍", "Heading2")]
        for beat in scene.get("beats", []):
            body.append(_doc_p(f"{beat.get('beat_id')}｜{beat.get('change')}｜{_string(beat.get('evidence_refs'))}"))
        for heading, key in (("表演与调度", "performance_blocking"), ("声光色动作与特效", "department_plans"), ("连续性与重置", "continuity"), ("执行风险与备选", "execution_risks")):
            body += [_doc_p(heading, "Heading2"), _doc_p(_string(scene.get(key)))]
        body.append(_doc_p("分镜镜头表", "Heading2"))
        for shot in scene.get("shots", []):
            body.append(_doc_p(f"{shot['shot_id']}｜{shot['dramatic_purpose']}｜{shot['framing']}｜{shot['movement']}｜{shot['duration_seconds']}s"))
            body.append(_doc_p(f"表演：{shot['performance_target']}；调度：{shot['blocking']}；证据：{_string(shot['evidence_refs'])}"))
    body.append(_doc_p("决定日志", "Heading1"))
    for item in package.get("decision_log", []):
        body.append(_doc_p(f"{item.get('decision_id')}｜{item.get('topic')}｜用户决定：{item.get('user_decision')}｜影响：{item.get('impact')}"))
    body.append(_doc_p("来源附录", "Heading1"))
    for scene in package.get("scenes", []):
        body += [_doc_p(f"{scene['production_scene_code']} / {scene['scene_id']}", "Heading2"), _doc_p(scene.get("source_text", ""))]
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + "".join(body) + f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="{margins}" w:right="{margins}" w:bottom="{margins}" w:left="{margins}"/></w:sectPr></w:body></w:document>'
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style></w:styles>'
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        _zip_write(archive, "[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
        _zip_write(archive, "_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        _zip_write(archive, "word/document.xml", document)
        _zip_write(archive, "word/styles.xml", styles)
        _zip_write(archive, "word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        _zip_write(archive, "docProps/core.xml", f'<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>导演执行包</dc:title><dc:identifier>{digest}</dc:identifier></cp:coreProperties>')


def _cell(ref: str, value: Any) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(_string(value))}</t></is></c>'


def _col(index: int) -> str:
    label = ""
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


def _sheet(rows: list[list[Any]]) -> str:
    xml_rows = []
    for rindex, row in enumerate(rows, 1):
        cells = "".join(_cell(f"{_col(cindex)}{rindex}", value) for cindex, value in enumerate(row, 1))
        xml_rows.append(f'<row r="{rindex}">{cells}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>'


def render_xlsx(package: dict[str, Any], output: Path) -> None:
    digest = package["integrity"]["canonical_json_sha256"]
    sheets: list[tuple[str, list[list[Any]]]] = []
    for scene in package.get("scenes", []):
        rows = [[f"规范 JSON SHA-256: {digest}"], SHOT_FIELDS]
        rows.extend([[shot.get(field) for field in SHOT_FIELDS] for shot in scene.get("shots", [])])
        sheets.append((scene.get("worksheet_name") or scene["production_scene_code"], rows))
    decision_headers = ["decision_id", "topic", "positions", "chief_recommendation", "tradeoff", "user_decision", "impact", "status"]
    sheets.append(("决定日志", [[f"规范 JSON SHA-256: {digest}"], decision_headers] + [[item.get(key) for key in decision_headers] for item in package.get("decision_log", [])]))
    trace_headers = ["source_id", "source_hash", "scene_id", "evidence_refs", "note"]
    sheets.append(("来源追踪", [[f"规范 JSON SHA-256: {digest}"], trace_headers] + [[item.get(key) for key in trace_headers] for item in package.get("source_trace", [])]))
    workbook_sheets = "".join(f'<sheet name="{escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>' for index, (name, _) in enumerate(sheets, 1))
    relationships = "".join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(sheets) + 1))
    overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for index in range(1, len(sheets) + 1))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        _zip_write(archive, "[Content_Types].xml", f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{overrides}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
        _zip_write(archive, "_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        _zip_write(archive, "xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets></workbook>')
        _zip_write(archive, "xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>')
        for index, (_, rows) in enumerate(sheets, 1):
            _zip_write(archive, f"xl/worksheets/sheet{index}.xml", _sheet(rows))
        _zip_write(archive, "docProps/core.xml", f'<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>镜头表</dc:title><dc:identifier>{digest}</dc:identifier></cp:coreProperties>')


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-requirement", "validate-package"):
        item = sub.add_parser(name)
        item.add_argument("input", type=Path)
        item.add_argument("--breakdown", type=Path)
    seal = sub.add_parser("seal")
    seal.add_argument("input", type=Path); seal.add_argument("output", type=Path); seal.add_argument("--breakdown", type=Path)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("input", type=Path); materialize.add_argument("--docx", type=Path, required=True); materialize.add_argument("--xlsx", type=Path); materialize.add_argument("--breakdown", type=Path)
    args = parser.parse_args()
    value = load_json(args.input)
    breakdown = load_json(args.breakdown) if getattr(args, "breakdown", None) else None
    if args.command == "validate-requirement":
        errors = validate_requirement(value, breakdown)
    elif args.command == "validate-package":
        errors = validate_package(value, breakdown)
    elif args.command == "seal":
        if value.get("final_confirmation", {}).get("status") != "confirmed":
            errors = ["cannot seal before second-Grill final confirmation"]
        else:
            sealed = seal_package(value)
            errors = validate_package(sealed, breakdown)
            if not errors:
                write_json(args.output, sealed)
    else:
        errors = validate_package(value, breakdown)
        if not errors:
            if value.get("status") != "sealed":
                errors = ["only a sealed package may be materialized"]
            else:
                render_docx(value, args.docx)
                if args.xlsx:
                    render_xlsx(value, args.xlsx)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
