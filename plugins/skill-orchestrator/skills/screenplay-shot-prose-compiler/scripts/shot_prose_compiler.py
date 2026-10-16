#!/usr/bin/env python3
"""Validate and render one-shot-per-paragraph screenplay direction prose."""

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


PACKAGE_SCHEMA = "SceneDirectionPackageV1"
RECORD_SCHEMA = "ShotProseRecordCollectionV1"
STANDARD_VERSION = "shot-prose-standard-v1"
SHOT_ID_RE = re.compile(r"^(?P<code>[A-Z][A-Z0-9]*S\d{3})C(?P<number>\d{3})$")
SEGMENT_ID_RE = re.compile(r"^(?P<shot>[A-Z][A-Z0-9]*S\d{3}C\d{3})-(?P<number>[1-9]\d*)$")
UNRESOLVED_CAMERA_RE = re.compile(
    r"(?:待定|什么的|也可以|可任选|任选其一|或(?:中景|近景|远景|特写|平拍|仰拍|俯拍|侧拍))"
)
FORBIDDEN_PROSE_RE = re.compile(
    r"(?:提示词|负面提示词|模型参数|生成参数|@(?:图片|Image)|\bevidence\b|SHA-?256|\bscn-[\w-]+|\bbea-[\w-]+)",
    re.IGNORECASE,
)
FORBIDDEN_KEYS = {"prompt", "negative_prompt", "model_parameters", "image_generation"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def package_digest(package: dict[str, Any]) -> str:
    value = deepcopy(package)
    value["integrity"] = {"canonical_json_sha256": None}
    return hash_json(value)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", "" if value is None else str(value))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                errors.append(f"forbidden prompt/model field {path}.{key}")
            errors.extend(_walk_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return errors


def _display_id(record_id: str) -> str:
    match = re.search(r"(C\d{3}(?:-[1-9]\d*)?)$", record_id)
    return match.group(1) if match else ""


def _validate_segment_sequence(shot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    shot_id = str(shot.get("shot_id", ""))
    segments = shot.get("shot_segments")
    if segments is None:
        return errors
    if not isinstance(segments, list) or not segments:
        return [f"{shot_id}: shot_segments must be a non-empty list when present"]
    expected = [f"{shot_id}-{index}" for index in range(1, len(segments) + 1)]
    actual = [segment.get("segment_id") if isinstance(segment, dict) else None for segment in segments]
    if actual != expected:
        errors.append(f"{shot_id}: subshots must start at -1 and be contiguous")
    required = {
        "segment_id", "beat_ids", "evidence_refs", "framing", "angle",
        "camera_position", "movement", "subject_action", "performance_target",
        "dialogue", "sound", "last_state",
    }
    for segment in segments:
        if not isinstance(segment, dict):
            errors.append(f"{shot_id}: every shot segment must be an object")
            continue
        segment_id = str(segment.get("segment_id", ""))
        missing = sorted(required - set(segment))
        if missing:
            errors.append(f"{segment_id or shot_id}: missing segment fields: {', '.join(missing)}")
        for key in required - {"dialogue", "sound"}:
            value = segment.get(key)
            if key in {"beat_ids", "evidence_refs"}:
                if not isinstance(value, list) or not value:
                    errors.append(f"{segment_id or shot_id}: {key} must be non-empty")
            elif not _nonempty(value):
                errors.append(f"{segment_id or shot_id}: {key} must be non-empty")
    return errors


def validate_package(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if package.get("schema_version") != PACKAGE_SCHEMA:
        errors.append(f"package schema_version must be {PACKAGE_SCHEMA}")
    if package.get("status") != "sealed":
        errors.append("only a sealed SceneDirectionPackageV1 may be compiled")
    recorded = package.get("integrity", {}).get("canonical_json_sha256")
    if not isinstance(recorded, str) or recorded != package_digest(package):
        errors.append("source package canonical_json_sha256 is invalid")
    scenes = package.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 2:
        errors.append("source package must contain 1 or 2 scenes")
        scenes = []
    seen_records: set[str] = set()
    for scene in scenes:
        shots = scene.get("shots") if isinstance(scene, dict) else None
        if not isinstance(shots, list) or not shots:
            errors.append(f"{scene.get('scene_id') if isinstance(scene, dict) else '?'}: shots must be non-empty")
            continue
        for shot in shots:
            if not isinstance(shot, dict):
                errors.append("every source shot must be an object")
                continue
            shot_id = str(shot.get("shot_id", ""))
            if not SHOT_ID_RE.fullmatch(shot_id):
                errors.append(f"invalid source shot ID: {shot_id}")
            errors.extend(_validate_segment_sequence(shot))
            ids = [shot_id]
            if isinstance(shot.get("shot_segments"), list) and shot["shot_segments"]:
                ids = [str(item.get("segment_id", "")) for item in shot["shot_segments"] if isinstance(item, dict)]
            for record_id in ids:
                if record_id in seen_records:
                    errors.append(f"duplicate source record ID: {record_id}")
                seen_records.add(record_id)
    return sorted(set(errors))


def _source_records(package: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    records: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for scene in package.get("scenes", []):
        for shot in scene.get("shots", []):
            segments = shot.get("shot_segments")
            if isinstance(segments, list) and segments:
                records.extend((scene, shot, segment) for segment in segments)
            else:
                records.append((scene, shot, shot))
    return records


def _contains(prose: Any, value: Any) -> bool:
    expected = _normalized(value)
    return not expected or expected in _normalized(prose)


def validate_records(package: dict[str, Any], records: dict[str, Any]) -> list[str]:
    errors = validate_package(package)
    errors.extend(_walk_forbidden(records))
    if records.get("schema_version") != RECORD_SCHEMA:
        errors.append(f"records schema_version must be {RECORD_SCHEMA}")
    if records.get("standard_version") != STANDARD_VERSION:
        errors.append(f"standard_version must be {STANDARD_VERSION}")
    digest = package.get("integrity", {}).get("canonical_json_sha256")
    if records.get("source_package_sha256") != digest:
        errors.append("source_package_sha256 does not match the sealed package")

    source = _source_records(package) if not validate_package(package) else []
    expected_ids = [str(item[2].get("segment_id") or item[1].get("shot_id")) for item in source]
    source_by_id = {record_id: item for record_id, item in zip(expected_ids, source)}
    scene_values = records.get("scenes")
    if not isinstance(scene_values, list):
        errors.append("scenes must be a list")
        scene_values = []
    source_scenes = package.get("scenes", []) if isinstance(package.get("scenes"), list) else []
    if len(scene_values) != len(source_scenes):
        errors.append("record scenes must match source scene count")

    actual_ids: list[str] = []
    for index, scene in enumerate(scene_values):
        if not isinstance(scene, dict):
            errors.append("every record scene must be an object")
            continue
        if index >= len(source_scenes):
            continue
        source_scene = source_scenes[index]
        for key in ("scene_id", "production_scene_code", "title"):
            if scene.get(key) != source_scene.get(key):
                errors.append(f"scene {index + 1}: {key} does not match the source package")
        baseline = scene.get("baseline")
        required_baseline = ("director_intent", "space_axis", "weather_light", "ambient_sound", "initial_state")
        if not isinstance(baseline, dict) or any(not _nonempty(baseline.get(key)) for key in required_baseline):
            errors.append(f"{scene.get('scene_id')}: scene baseline is incomplete")
        scene_records = scene.get("records")
        if not isinstance(scene_records, list) or not scene_records:
            errors.append(f"{scene.get('scene_id')}: records must be non-empty")
            continue
        for record in scene_records:
            if not isinstance(record, dict):
                errors.append("every prose record must be an object")
                continue
            record_id = str(record.get("record_id", ""))
            actual_ids.append(record_id)
            source_tuple = source_by_id.get(record_id)
            if source_tuple is None:
                errors.append(f"unknown prose record ID: {record_id}")
                continue
            source_scene_item, source_shot, source_item = source_tuple
            shot_group_id = str(source_shot.get("shot_id", ""))
            if record.get("shot_group_id") != shot_group_id:
                errors.append(f"{record_id}: shot_group_id does not match the source shot")
            if record.get("display_id") != _display_id(record_id):
                errors.append(f"{record_id}: display_id must be {_display_id(record_id)}")
            if scene.get("scene_id") != source_scene_item.get("scene_id"):
                errors.append(f"{record_id}: record is in the wrong scene")
            for key in ("beat_ids", "evidence_refs"):
                if record.get(key) != source_item.get(key):
                    errors.append(f"{record_id}: {key} must exactly match the source")
            camera = record.get("camera_contract")
            if not isinstance(camera, dict):
                errors.append(f"{record_id}: camera_contract is required")
                camera = {}
            if camera.get("framing") != source_item.get("framing"):
                errors.append(f"{record_id}: framing must exactly match the source")
            if camera.get("shooting_relation") != source_item.get("camera_position"):
                errors.append(f"{record_id}: shooting_relation must exactly match source camera_position")
            for camera_value in camera.values():
                if isinstance(camera_value, str) and UNRESOLVED_CAMERA_RE.search(camera_value):
                    errors.append(f"{record_id}: unresolved camera alternative is forbidden")
            if record.get("visual_action") != source_item.get("subject_action"):
                errors.append(f"{record_id}: visual_action must exactly match source subject_action")
            performance = record.get("performance")
            if not isinstance(performance, dict) or performance.get("externalization") != source_item.get("performance_target"):
                errors.append(f"{record_id}: performance externalization must exactly match the source")
            if record.get("dialogue") != source_item.get("dialogue", ""):
                errors.append(f"{record_id}: dialogue must exactly match the source")
            if record.get("end_state") != source_item.get("last_state"):
                errors.append(f"{record_id}: end_state must exactly match the source")
            sound_events = record.get("sound_events")
            if not isinstance(sound_events, list) or any(not _nonempty(item) for item in sound_events):
                errors.append(f"{record_id}: sound_events must contain only non-empty strings")
                sound_events = []
            source_sound = source_item.get("sound")
            if _nonempty(source_sound) and not any(_contains(item, source_sound) for item in sound_events):
                errors.append(f"{record_id}: source sound is missing from sound_events")
            prose = record.get("prose")
            if not _nonempty(prose):
                errors.append(f"{record_id}: prose is required")
                continue
            if FORBIDDEN_PROSE_RE.search(prose):
                errors.append(f"{record_id}: prose contains prompt, model, audit, or internal evidence text")
            if UNRESOLVED_CAMERA_RE.search(prose):
                errors.append(f"{record_id}: prose contains an unresolved technical alternative")
            if re.search(r"[A-Z][A-Z0-9]*S\d{3}C\d{3}", prose):
                errors.append(f"{record_id}: prose must not expose full internal shot IDs")
            for label, value in (
                ("framing", camera.get("framing")),
                ("shooting_relation", camera.get("shooting_relation")),
                ("visual_action", record.get("visual_action")),
                ("performance_externalization", performance.get("externalization") if isinstance(performance, dict) else ""),
                ("dialogue", record.get("dialogue")),
                ("end_state", record.get("end_state")),
            ):
                if not _contains(prose, value):
                    errors.append(f"{record_id}: prose omits {label}")
            for sound_event in sound_events:
                if not _contains(prose, sound_event):
                    errors.append(f"{record_id}: prose omits sound event")

    if actual_ids != expected_ids:
        errors.append("prose records must exactly preserve source shot/subshot order")

    calibration = records.get("calibration")
    if not isinstance(calibration, dict) or calibration.get("status") != "confirmed" or not _nonempty(calibration.get("confirmed_at")):
        errors.append("the prose calibration gate must be confirmed")
    else:
        mode = calibration.get("mode")
        samples = calibration.get("sample_record_ids")
        if mode not in {"three_sample", "inherited"}:
            errors.append("calibration mode must be three_sample or inherited")
        if not isinstance(samples, list) or len(samples) != len(set(samples)) or any(item not in expected_ids for item in samples):
            errors.append("calibration sample_record_ids must be unique valid record IDs")
        elif mode == "three_sample":
            required_count = min(3, len(expected_ids))
            if len(samples) != required_count:
                errors.append(f"three_sample calibration requires {required_count} representative record IDs")
    return sorted(set(errors))


def _zip_write(archive: zipfile.ZipFile, name: str, data: str) -> None:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data.encode("utf-8"))


def _runs(text: str, *, bold_prefix: str | None = None) -> str:
    if bold_prefix is None:
        return f'<w:r><w:rPr><w:rFonts w:ascii="Songti SC" w:hAnsi="Songti SC" w:eastAsia="Songti SC" w:hint="eastAsia"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    remainder = text[len(bold_prefix):]
    return (
        f'<w:r><w:rPr><w:rFonts w:ascii="Songti SC" w:hAnsi="Songti SC" w:eastAsia="Songti SC" w:hint="eastAsia"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr><w:t>{escape(bold_prefix)}</w:t></w:r>'
        f'<w:r><w:rPr><w:rFonts w:ascii="Songti SC" w:hAnsi="Songti SC" w:eastAsia="Songti SC" w:hint="eastAsia"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr><w:t xml:space="preserve">{escape(remainder)}</w:t></w:r>'
    )


def _paragraph(text: str, *, bold_prefix: str | None = None, heading: bool = False, after: int = 180) -> str:
    ppr = (
        f'<w:pPr><w:spacing w:line="360" w:lineRule="auto" w:after="{after}"/>'
        + ('<w:keepNext/><w:outlineLvl w:val="0"/>' if heading else '')
        + '</w:pPr>'
    )
    runs = _runs(text, bold_prefix=bold_prefix)
    if heading:
        runs = runs.replace('<w:rPr>', '<w:rPr><w:b/>', 1)
    return f'<w:p>{ppr}{runs}</w:p>'


def render_docx(package: dict[str, Any], records: dict[str, Any], output: Path) -> None:
    body: list[str] = []
    for scene in records.get("scenes", []):
        code = str(scene["production_scene_code"])
        code_match = re.match(r"^(?P<episode>[A-Z][A-Z0-9]*)(?P<scene>S\d{3})$", code)
        visible_code = f"{code_match.group('episode')} {code_match.group('scene')}" if code_match else code
        title = f"{visible_code} {scene.get('title', '')}".strip()
        body.append(_paragraph(title, heading=True, after=240))
        baseline = scene["baseline"]
        baseline_text = (
            "导演基线："
            f"{baseline['director_intent']}；{baseline['space_axis']}；{baseline['weather_light']}；"
            f"持续环境声为{baseline['ambient_sound']}；{baseline['initial_state']}。"
        )
        body.append(_paragraph(baseline_text, after=240))
        for record in scene.get("records", []):
            prefix = f"{record['display_id']}　"
            body.append(_paragraph(prefix + record["prose"].strip(), bold_prefix=prefix, after=220))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Songti SC" w:hAnsi="Songti SC" w:eastAsia="Songti SC" w:hint="eastAsia"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '</w:styles>'
    )
    digest = str(package["integrity"]["canonical_json_sha256"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        _zip_write(archive, "[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
        _zip_write(archive, "_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        _zip_write(archive, "word/document.xml", document)
        _zip_write(archive, "word/styles.xml", styles)
        _zip_write(archive, "word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        _zip_write(archive, "docProps/core.xml", f'<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>一镜一段导演分镜正文</dc:title><dc:identifier>{digest}</dc:identifier></cp:coreProperties>')


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("package", type=Path)
    validate.add_argument("records", type=Path)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("package", type=Path)
    materialize.add_argument("records", type=Path)
    materialize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = load_json(args.package)
    records = load_json(args.records)
    errors = validate_records(package, records)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.command == "materialize":
        render_docx(package, records, args.output)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
