#!/usr/bin/env python3
"""Normalize text-native screenplay formats into a traceable JSON scene map.

PDF and DOCX are intentionally routed to Codex's layout-aware document skills.
This tool uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_FORMATS = {"text", "txt", "markdown", "fountain", "fdx"}
ROUTED_FORMATS = {"pdf", "docx"}
EXTENSION_FORMATS = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".fountain": "fountain",
    ".spmd": "fountain",
    ".fdx": "fdx",
    ".pdf": "pdf",
    ".docx": "docx",
}

SCENE_NUMBER_RE = re.compile(r"\s+#([^#]+)#\s*$")
EN_SCENE_RE = re.compile(
    r"^(?:INT\.?|EXT\.?|INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|EST\.?)\s+",
    re.IGNORECASE,
)
ZH_SCENE_RE = re.compile(
    r"^(?:(?:第?\s*\d+[A-Za-z]?\s*[场場])|(?:场景\s*\d*)|内景|外景|内/外景?|外/内景?)(?:\s|[：:.-])",
    re.IGNORECASE,
)
ZH_NUMBERED_SCENE_RE = re.compile(
    r"^\d+[A-Za-z]?\s*[.、]\s*(?:(?:日|夜|晨|昏|黄昏)\s*)?(?:内|外)(?:\s|[，,.-])"
)
TRANSITION_RE = re.compile(
    r"^(?:FADE (?:IN|OUT)|CUT TO|DISSOLVE TO|SMASH CUT TO|MATCH CUT TO)\s*:?$",
    re.IGNORECASE,
)
ZH_TRANSITION_RE = re.compile(r"^(?:切至|淡入|淡出|叠化|闪切|匹配剪辑)\s*[：:]?$", re.IGNORECASE)
INLINE_DIALOGUE_RE = re.compile(
    r"^([A-Za-z0-9_\-·\u3400-\u9fff]{1,24})(?:\s*[（(][^）)]{1,20}[）)])?\s*[：:]\s*(.+)$"
)


class RoutedFormatError(ValueError):
    """Raised when a layout-aware route is required."""


@dataclass
class Element:
    type: str
    text: str
    start: int
    end: int
    character_name: str | None = None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def detect_format(path: str, explicit: str | None) -> str:
    if explicit:
        fmt = explicit.lower()
    elif path == "-":
        fmt = "text"
    else:
        fmt = EXTENSION_FORMATS.get(Path(path).suffix.lower(), "text")
    if fmt in ROUTED_FORMATS:
        raise RoutedFormatError(
            f"{fmt.upper()} requires the Codex {'PDF' if fmt == 'pdf' else 'Documents'} "
            "capability for layout-aware extraction and visual verification; "
            "extract to text first, preserve page/paragraph anchors, then pass the text via stdin."
        )
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {fmt}")
    return fmt


def read_source(path: str) -> tuple[str, str | None]:
    if path == "-":
        return sys.stdin.read(), None
    source_path = Path(path)
    return source_path.read_text(encoding="utf-8-sig"), source_path.name


def strip_scene_number(heading: str) -> tuple[str, str | None]:
    match = SCENE_NUMBER_RE.search(heading)
    if not match:
        return heading.strip(), None
    return heading[: match.start()].rstrip(), match.group(1).strip()


def is_scene_heading(line: str) -> bool:
    candidate = line.strip()
    if not candidate:
        return False
    if candidate.startswith(".") and not candidate.startswith(".."):
        return True
    candidate, _ = strip_scene_number(candidate)
    return bool(
        EN_SCENE_RE.match(candidate)
        or ZH_SCENE_RE.match(candidate)
        or ZH_NUMBERED_SCENE_RE.match(candidate)
    )


def parse_heading(raw_heading: str) -> dict[str, str | None]:
    heading = raw_heading.strip()
    if heading.startswith(".") and not heading.startswith(".."):
        heading = heading[1:].lstrip()
    heading, scene_number = strip_scene_number(heading)
    upper = heading.upper()
    int_ext: str | None = None
    for prefix, value in (
        ("INT./EXT.", "INT_EXT"),
        ("INT/EXT.", "INT_EXT"),
        ("EXT./INT.", "INT_EXT"),
        ("EXT/INT.", "INT_EXT"),
        ("I/E.", "INT_EXT"),
        ("INT.", "INT"),
        ("INT ", "INT"),
        ("EXT.", "EXT"),
        ("EXT ", "EXT"),
    ):
        if upper.startswith(prefix):
            int_ext = value
            break
    if int_ext is None:
        if "内/外" in heading or "外/内" in heading:
            int_ext = "INT_EXT"
        elif "内景" in heading or re.search(r"(?:^|[.、\s])内(?:$|[，,\s.-])", heading):
            int_ext = "INT"
        elif "外景" in heading or re.search(r"(?:^|[.、\s])外(?:$|[，,\s.-])", heading):
            int_ext = "EXT"

    time_of_day: str | None = None
    time_tokens = {
        "DAY": "DAY",
        "NIGHT": "NIGHT",
        "MORNING": "MORNING",
        "EVENING": "EVENING",
        "DAWN": "DAWN",
        "DUSK": "DUSK",
        "日": "DAY",
        "白天": "DAY",
        "夜": "NIGHT",
        "夜晚": "NIGHT",
        "晨": "MORNING",
        "清晨": "DAWN",
        "黄昏": "DUSK",
        "昏": "DUSK",
    }
    for token, normalized in time_tokens.items():
        if re.search(rf"(?:^|[\s—–\-,.、]){re.escape(token)}(?:$|[\s—–\-,.、])", upper if token.isascii() else heading):
            time_of_day = normalized
            break

    location = heading
    location = re.sub(
        r"^(?:INT\.?|EXT\.?|INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|EST\.?)\s+",
        "",
        location,
        flags=re.IGNORECASE,
    )
    location = re.sub(r"^(?:内景|外景|内/外景?|外/内景?)\s*[：:.-]?\s*", "", location)
    location = re.sub(r"^\d+[A-Za-z]?\s*[.、]\s*(?:(?:日|夜|晨|昏|黄昏)\s*)?(?:内|外)\s*", "", location)
    location = re.split(r"\s+[—–-]\s+", location, maxsplit=1)[0].strip()
    for token in ("白天", "夜晚", "清晨", "黄昏", "DAY", "NIGHT", "MORNING", "EVENING", "DAWN", "DUSK"):
        location = re.sub(rf"(?:^|\s){re.escape(token)}$", "", location, flags=re.IGNORECASE).strip()

    return {
        "heading": heading,
        "scene_number": scene_number,
        "int_ext": int_ext,
        "location": location or None,
        "time_of_day": time_of_day,
    }


def is_character_cue(line: str) -> bool:
    candidate = line.strip()
    if not candidate or len(candidate) > 60:
        return False
    if candidate.startswith("@"):
        return True
    core = re.sub(r"\s*[\^]$", "", candidate)
    core = re.sub(r"\s*\([^)]*\)\s*$", "", core).strip()
    letters = [char for char in core if char.isalpha() and char.isascii()]
    if not letters:
        return False
    return core == core.upper() and not core.endswith((".", "!", "?", ":", ";"))


def character_name_from_cue(line: str) -> str:
    name = line.strip().lstrip("@").rstrip("^").strip()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    return name


def make_ref(prefix: str, start: int, end: int) -> str:
    return f"{prefix}{start}" if start == end else f"{prefix}{start}-{prefix}{end}"


def parse_fountain_or_text(text: str, fmt: str) -> tuple[list[Element], list[str], str]:
    lines = text.split("\n")
    elements: list[Element] = []
    warnings: list[str] = []
    dialogue_mode = False
    previous_blank = True

    for index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            dialogue_mode = False
            previous_blank = True
            continue
        if is_scene_heading(stripped):
            elements.append(Element("scene_heading", stripped, index, index))
            dialogue_mode = False
        elif TRANSITION_RE.match(stripped) or ZH_TRANSITION_RE.match(stripped) or (
            stripped.endswith("TO:") and stripped == stripped.upper()
        ):
            elements.append(Element("transition", stripped, index, index))
            dialogue_mode = False
        elif previous_blank and is_character_cue(stripped):
            name = character_name_from_cue(stripped)
            elements.append(Element("character", stripped, index, index, name))
            dialogue_mode = True
        elif dialogue_mode and stripped.startswith("(") and stripped.endswith(")"):
            elements.append(Element("parenthetical", stripped, index, index))
        elif dialogue_mode:
            elements.append(Element("dialogue", raw_line.rstrip(), index, index))
        else:
            inline = INLINE_DIALOGUE_RE.match(stripped)
            if inline and len(inline.group(1)) <= 16:
                elements.append(Element("dialogue_inline", raw_line.rstrip(), index, index, inline.group(1)))
            else:
                elements.append(Element("action", raw_line.rstrip(), index, index))
        previous_blank = False

    if fmt in {"text", "txt", "markdown"} and not any(element.type == "scene_heading" for element in elements):
        warnings.append("no_explicit_scene_headings")
    return elements, warnings, "L"


def iter_fdx_paragraphs(root: ET.Element) -> Iterable[ET.Element]:
    content = next((node for node in root.iter() if local_name(node.tag) == "Content"), None)
    scope = content if content is not None else root
    for node in scope.iter():
        if local_name(node.tag) == "Paragraph":
            yield node


def parse_fdx(text: str) -> tuple[list[Element], list[str], str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid FDX XML: {exc}") from exc

    type_map = {
        "scene heading": "scene_heading",
        "action": "action",
        "character": "character",
        "dialogue": "dialogue",
        "parenthetical": "parenthetical",
        "transition": "transition",
        "shot": "shot",
        "general": "action",
    }
    elements: list[Element] = []
    warnings: list[str] = []
    unknown_types: set[str] = set()
    for index, paragraph in enumerate(iter_fdx_paragraphs(root), start=1):
        raw_type = paragraph.attrib.get("Type", "General").strip()
        element_type = type_map.get(raw_type.lower(), "unknown")
        paragraph_text = "".join(paragraph.itertext()).strip()
        if not paragraph_text:
            continue
        if element_type == "unknown":
            unknown_types.add(raw_type or "<missing>")
            element_type = "action"
        character_name = character_name_from_cue(paragraph_text) if element_type == "character" else None
        elements.append(Element(element_type, paragraph_text, index, index, character_name))
    if unknown_types:
        warnings.append("unknown_fdx_paragraph_types:" + ",".join(sorted(unknown_types)))
    return elements, warnings, "P"


def build_scenes(elements: list[Element], ref_prefix: str, warnings: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    heading_indices = [index for index, element in enumerate(elements) if element.type == "scene_heading"]
    unassigned_ranges: list[str] = []
    if not elements:
        return [], unassigned_ranges

    if not heading_indices:
        first, last = elements[0], elements[-1]
        scene_elements = elements
        warnings.append("inferred_single_scene")
        return [
            scene_record(
                1,
                None,
                scene_elements,
                first.start,
                last.end,
                ref_prefix,
                certainty="inferred",
            )
        ], unassigned_ranges

    if heading_indices[0] > 0:
        preamble = elements[: heading_indices[0]]
        unassigned_ranges.append(make_ref(ref_prefix, preamble[0].start, preamble[-1].end))
        warnings.append("unassigned_preamble_before_first_scene")

    scenes: list[dict[str, Any]] = []
    for scene_index, heading_index in enumerate(heading_indices, start=1):
        next_heading_index = heading_indices[scene_index] if scene_index < len(heading_indices) else len(elements)
        group = elements[heading_index:next_heading_index]
        heading_element = group[0]
        scenes.append(
            scene_record(
                scene_index,
                heading_element,
                group,
                group[0].start,
                group[-1].end,
                ref_prefix,
                certainty="explicit",
            )
        )
    return scenes, unassigned_ranges


def scene_record(
    index: int,
    heading_element: Element | None,
    elements: list[Element],
    start: int,
    end: int,
    ref_prefix: str,
    certainty: str,
) -> dict[str, Any]:
    parsed = parse_heading(heading_element.text) if heading_element else {
        "heading": "",
        "scene_number": None,
        "int_ext": None,
        "location": None,
        "time_of_day": None,
    }
    return {
        "id": f"scn-{index:03d}",
        **parsed,
        "certainty": certainty,
        "source_refs": [make_ref(ref_prefix, start, end)],
        "source_range": {"start": start, "end": end, "unit": "line" if ref_prefix == "L" else "paragraph"},
        "text": "\n".join(element.text for element in elements),
        "elements": [
            {
                "type": element.type,
                "text": element.text,
                "source_refs": [make_ref(ref_prefix, element.start, element.end)],
                **({"character_name": element.character_name} if element.character_name else {}),
            }
            for element in elements
        ],
    }


def entity_records(scenes: list[dict[str, Any]], entity_type: str) -> list[dict[str, Any]]:
    occurrences: dict[str, dict[str, Any]] = {}
    if entity_type == "characters":
        for scene in scenes:
            for element in scene["elements"]:
                name = element.get("character_name")
                if not name:
                    continue
                key = name.casefold()
                record = occurrences.setdefault(key, {"name": name, "scene_ids": [], "source_refs": []})
                if scene["id"] not in record["scene_ids"]:
                    record["scene_ids"].append(scene["id"])
                record["source_refs"].extend(
                    ref for ref in element["source_refs"] if ref not in record["source_refs"]
                )
    elif entity_type == "locations":
        for scene in scenes:
            name = scene.get("location")
            if not name:
                continue
            key = name.casefold()
            record = occurrences.setdefault(key, {"name": name, "scene_ids": [], "source_refs": []})
            record["scene_ids"].append(scene["id"])
            record["source_refs"].extend(scene["source_refs"])

    prefix = "chr" if entity_type == "characters" else "loc"
    return [
        {
            "id": f"{prefix}-{index:03d}",
            "name": record["name"],
            "scene_ids": record["scene_ids"],
            "source_refs": record["source_refs"],
            "certainty": "explicit",
        }
        for index, (_, record) in enumerate(sorted(occurrences.items()), start=1)
    ]


def normalize_screenplay(
    source_text: str,
    fmt: str,
    source_id: str,
    draft_id: str,
    filename: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    text = normalize_text(source_text)
    if not text.strip():
        raise ValueError("Screenplay source is empty after normalization")
    if fmt == "fdx":
        elements, warnings, ref_prefix = parse_fdx(text)
    else:
        elements, warnings, ref_prefix = parse_fountain_or_text(text, fmt)
    scenes, unassigned_ranges = build_scenes(elements, ref_prefix, warnings)
    if not scenes:
        raise ValueError("No usable screenplay content was found")
    quality = "degraded" if warnings else "good"
    manifest = {
        "source_id": source_id,
        "draft_id": draft_id,
        "filename": filename,
        "title": title,
        "format": fmt,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "line_count": len(text.split("\n")) if ref_prefix == "L" else None,
        "paragraph_count": len(elements) if ref_prefix == "P" else None,
        "character_count": len(text),
        "extraction_quality": quality,
        "reference_scheme": "line" if ref_prefix == "L" else "fdx_paragraph",
        "warnings": warnings,
    }
    characters = entity_records(scenes, "characters")
    locations = entity_records(scenes, "locations")
    return {
        "schema_version": "1.0.0",
        "source_manifest": manifest,
        "scenes": scenes,
        "characters": characters,
        "locations": locations,
        "props": [],
        "effects": [],
        "coverage": {
            "scene_count": len(scenes),
            "source_start": elements[0].start,
            "source_end": elements[-1].end,
            "reference_scheme": manifest["reference_scheme"],
            "unassigned_ranges": unassigned_ranges,
        },
    }


def write_json(data: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Source path, or - for stdin")
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS | ROUTED_FORMATS))
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--output", help="Write JSON to this path; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fmt = detect_format(args.source, args.format)
        raw_text, filename = read_source(args.source)
        result = normalize_screenplay(raw_text, fmt, args.source_id, args.draft_id, filename, args.title)
        write_json(result, args.output)
    except RoutedFormatError as exc:
        print(f"ROUTE_REQUIRED: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
