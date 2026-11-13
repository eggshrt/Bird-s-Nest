#!/usr/bin/env python3
"""Compare normalized screenplay drafts and preserve high-confidence scene IDs.

Inputs are JSON files produced by normalize_screenplay.py. Matching is
deterministic and conservative: ambiguous candidates are reported for review.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any


AUTO_MATCH_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.50
DECISIVE_GAP = 0.08


def load_json(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    if not isinstance(data.get("scenes"), list):
        raise ValueError(f"Missing scenes array: {path}")
    return data


def compact_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\u3400-\u9fff ]+", "", value)
    return value.strip()


def scene_similarity(old_scene: dict[str, Any], new_scene: dict[str, Any]) -> float:
    old_text = compact_text(old_scene.get("text") or old_scene.get("summary"))
    new_text = compact_text(new_scene.get("text") or new_scene.get("summary"))
    old_heading = compact_text(old_scene.get("heading"))
    new_heading = compact_text(new_scene.get("heading"))
    text_score = difflib.SequenceMatcher(None, old_text, new_text).ratio()
    heading_score = difflib.SequenceMatcher(None, old_heading, new_heading).ratio()
    if not old_heading and not new_heading:
        return text_score
    return round((text_score * 0.75) + (heading_score * 0.25), 6)


def scene_number(scene: dict[str, Any]) -> str:
    value = scene.get("scene_number")
    return compact_text(str(value)) if value is not None else ""


def heading_key(scene: dict[str, Any]) -> str:
    return compact_text(scene.get("heading"))


def unique_index(scenes: list[dict[str, Any]], key_fn: Any) -> dict[str, int]:
    buckets: dict[str, list[int]] = {}
    for index, scene in enumerate(scenes):
        key = key_fn(scene)
        if key:
            buckets.setdefault(key, []).append(index)
    return {key: indexes[0] for key, indexes in buckets.items() if len(indexes) == 1}


def make_match(
    old_scene: dict[str, Any],
    new_scene: dict[str, Any],
    basis: str,
    confidence: str,
) -> dict[str, Any]:
    similarity = scene_similarity(old_scene, new_scene)
    old_heading = compact_text(old_scene.get("heading"))
    new_heading = compact_text(new_scene.get("heading"))
    old_text = compact_text(old_scene.get("text") or old_scene.get("summary"))
    new_text = compact_text(new_scene.get("text") or new_scene.get("summary"))
    heading_changed = old_heading != new_heading
    text_changed = old_text != new_text
    return {
        "old_scene_id": old_scene["id"],
        "new_scene_id": new_scene["id"],
        "retained_scene_id": old_scene["id"],
        "match_basis": basis,
        "confidence": confidence,
        "similarity": similarity,
        "change_type": "modified" if heading_changed or text_changed else "unchanged",
        "heading_changed": heading_changed,
        "text_changed": text_changed,
    }


def match_scenes(
    old_scenes: list[dict[str, Any]], new_scenes: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int], set[int]]:
    matches: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()

    old_numbers = unique_index(old_scenes, scene_number)
    new_numbers = unique_index(new_scenes, scene_number)
    for number in sorted(set(old_numbers) & set(new_numbers)):
        old_index = old_numbers[number]
        new_index = new_numbers[number]
        matches.append(make_match(old_scenes[old_index], new_scenes[new_index], "scene_number", "high"))
        used_old.add(old_index)
        used_new.add(new_index)

    old_headings = unique_index(old_scenes, heading_key)
    new_headings = unique_index(new_scenes, heading_key)
    for heading in sorted(set(old_headings) & set(new_headings)):
        old_index = old_headings[heading]
        new_index = new_headings[heading]
        if old_index in used_old or new_index in used_new:
            continue
        matches.append(make_match(old_scenes[old_index], new_scenes[new_index], "heading", "high"))
        used_old.add(old_index)
        used_new.add(new_index)

    for new_index, new_scene in enumerate(new_scenes):
        if new_index in used_new:
            continue
        candidates = sorted(
            (
                (scene_similarity(old_scene, new_scene), old_index)
                for old_index, old_scene in enumerate(old_scenes)
                if old_index not in used_old
            ),
            reverse=True,
        )
        if not candidates:
            continue
        best_score, best_old_index = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        if best_score >= AUTO_MATCH_THRESHOLD and best_score - second_score >= DECISIVE_GAP:
            matches.append(
                make_match(old_scenes[best_old_index], new_scene, "text_similarity", "medium")
            )
            used_old.add(best_old_index)
            used_new.add(new_index)
        elif best_score >= AMBIGUOUS_THRESHOLD:
            candidate_ids = [
                old_scenes[old_index]["id"]
                for score, old_index in candidates
                if score >= max(AMBIGUOUS_THRESHOLD, best_score - DECISIVE_GAP)
            ]
            ambiguous.append(
                {
                    "new_scene_id": new_scene["id"],
                    "candidate_old_scene_ids": candidate_ids,
                    "best_similarity": best_score,
                    "reason": "Similarity is plausible but not decisive enough to retain an ID automatically.",
                }
            )

    matches.sort(key=lambda item: item["new_scene_id"])
    return matches, ambiguous, used_old, used_new


def id_number(scene_id: str) -> int:
    match = re.search(r"(\d+)$", scene_id)
    return int(match.group(1)) if match else 0


def allocate_scene_ids(
    old_scenes: list[dict[str, Any]],
    new_scenes: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> dict[str, str]:
    mapping = {match["new_scene_id"]: match["retained_scene_id"] for match in matches}
    next_number = max((id_number(scene["id"]) for scene in old_scenes), default=0) + 1
    for scene in new_scenes:
        if scene["id"] not in mapping:
            mapping[scene["id"]] = f"scn-{next_number:03d}"
            next_number += 1
    return mapping


def scene_ref(scene: dict[str, Any], scene_id: str | None = None) -> dict[str, Any]:
    return {
        "scene_id": scene_id or scene["id"],
        "heading": scene.get("heading", ""),
        "source_refs": scene.get("source_refs", []),
        "scene_number": scene.get("scene_number"),
    }


def entity_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct = data.get(key)
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    nested = data.get("entities", {}).get(key) if isinstance(data.get("entities"), dict) else None
    return [item for item in nested if isinstance(item, dict)] if isinstance(nested, list) else []


def comparable_entity(entity: dict[str, Any]) -> str:
    ignored = {"id", "source_refs", "scene_ids"}
    payload = {key: value for key, value in entity.items() if key not in ignored}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def entity_change_set(old_data: dict[str, Any], new_data: dict[str, Any], key: str) -> dict[str, list[str]]:
    old_map = {compact_text(item.get("name")): item for item in entity_list(old_data, key) if item.get("name")}
    new_map = {compact_text(item.get("name")): item for item in entity_list(new_data, key) if item.get("name")}
    return {
        "added": sorted(new_map[name].get("name", name) for name in set(new_map) - set(old_map)),
        "removed": sorted(old_map[name].get("name", name) for name in set(old_map) - set(new_map)),
        "changed": sorted(
            new_map[name].get("name", name)
            for name in set(old_map) & set(new_map)
            if comparable_entity(old_map[name]) != comparable_entity(new_map[name])
        ),
    }


def draft_ref(data: dict[str, Any]) -> dict[str, Any]:
    manifest = data.get("source_manifest", {})
    return {
        "source_id": manifest.get("source_id", "unknown"),
        "draft_id": manifest.get("draft_id", "unknown"),
        "sha256": manifest.get("sha256", "0" * 64),
    }


def role_impacts(
    matches: list[dict[str, Any]],
    added: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    entity_changes: dict[str, dict[str, list[str]]],
) -> list[dict[str, Any]]:
    modified = [item for item in matches if item["change_type"] == "modified"]
    changed_scene_ids = sorted(
        {item["retained_scene_id"] for item in modified}
        | {item["scene_id"] for item in added}
        | {item["scene_id"] for item in removed}
    )
    if not changed_scene_ids and not any(
        values for group in entity_changes.values() for values in group.values()
    ):
        return []

    impacts: dict[str, set[str]] = {
        "chief_director": {"Story-wide alignment or approvals may have changed."},
        "director": {"Scene intent, beats, or continuity require review."},
        "executive_director": {"Generation tasks and dependencies require re-planning."},
        "continuity": {"Entry/exit and cross-scene state require reconciliation."},
    }
    if modified or added or removed:
        impacts.update(
            {
                "performance_execution": {"Performance actions or state handoffs may have changed."},
                "storyboard": {"Shot blueprints and transition handoffs may be invalidated."},
                "editing": {"Timing, reaction, or sequence structure may have changed."},
                "sound_music": {"Dialogue, sound timing, or transitions may have changed."},
            }
        )
    if any(match["heading_changed"] for match in modified) or any(
        entity_changes["locations"][name] for name in ("added", "removed", "changed")
    ):
        impacts.setdefault("art", set()).add("Location or visual asset states require review.")
        impacts.setdefault("cinematography_lighting", set()).add(
            "Spatial, light, or coverage assumptions may have changed."
        )
    if any(entity_changes["characters"][name] for name in ("added", "removed", "changed")):
        impacts.setdefault("art", set()).add("Character identity or wardrobe assets require review.")
        impacts.setdefault("performance_execution", set()).add(
            "Character performance continuity requires review."
        )
    if any(entity_changes["props"][name] for name in ("added", "removed", "changed")):
        impacts.setdefault("art", set()).add("Prop assets and states require review.")
        impacts.setdefault("storyboard", set()).add("Prop interaction and handoff require review.")
    if any(entity_changes["effects"][name] for name in ("added", "removed", "changed")):
        impacts.setdefault("vfx", set()).add("Effects scope or compositing assumptions changed.")

    return [
        {
            "role_id": role_id,
            "scene_ids": changed_scene_ids,
            "reasons": sorted(reasons),
            "required_action": "Re-run the affected role for changed scenes and re-approve invalidated handoffs.",
        }
        for role_id, reasons in sorted(impacts.items())
    ]


def rewrite_new_draft(new_data: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    rewritten = copy.deepcopy(new_data)
    for scene in rewritten.get("scenes", []):
        old_id = scene["id"]
        scene["id"] = mapping[old_id]

    def rewrite_scene_ids(items: list[dict[str, Any]]) -> None:
        for item in items:
            if isinstance(item.get("scene_ids"), list):
                item["scene_ids"] = [mapping.get(scene_id, scene_id) for scene_id in item["scene_ids"]]

    for key in ("characters", "locations", "props", "effects"):
        items = rewritten.get(key)
        if isinstance(items, list):
            rewrite_scene_ids(items)
    if isinstance(rewritten.get("entities"), dict):
        for key in ("characters", "locations", "props", "effects"):
            items = rewritten["entities"].get(key)
            if isinstance(items, list):
                rewrite_scene_ids(items)
    coverage = rewritten.get("coverage")
    if isinstance(coverage, dict):
        for key in ("requested_scene_ids", "completed_scene_ids", "pending_scene_ids"):
            if isinstance(coverage.get(key), list):
                coverage[key] = [mapping.get(scene_id, scene_id) for scene_id in coverage[key]]
    return rewritten


def compare_drafts(old_data: dict[str, Any], new_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    old_scenes = old_data["scenes"]
    new_scenes = new_data["scenes"]
    matches, ambiguous, used_old, used_new = match_scenes(old_scenes, new_scenes)
    mapping = allocate_scene_ids(old_scenes, new_scenes, matches)
    ambiguous_new_ids = {item["new_scene_id"] for item in ambiguous}
    ambiguous_old_ids = {
        scene_id
        for item in ambiguous
        for scene_id in item["candidate_old_scene_ids"]
    }

    added = [
        scene_ref(scene, mapping[scene["id"]])
        for index, scene in enumerate(new_scenes)
        if index not in used_new and scene["id"] not in ambiguous_new_ids
    ]
    removed = [
        scene_ref(scene)
        for index, scene in enumerate(old_scenes)
        if index not in used_old and scene["id"] not in ambiguous_old_ids
    ]
    entity_changes = {
        key: entity_change_set(old_data, new_data, key)
        for key in ("characters", "locations", "props", "effects")
    }
    unchanged_count = sum(match["change_type"] == "unchanged" for match in matches)
    modified_count = sum(match["change_type"] == "modified" for match in matches)
    impact = {
        "schema_version": "1.0.0",
        "old_draft": draft_ref(old_data),
        "new_draft": draft_ref(new_data),
        "matches": matches,
        "added_scenes": added,
        "removed_scenes": removed,
        "ambiguous_matches": ambiguous,
        "entity_changes": entity_changes,
        "role_impacts": role_impacts(matches, added, removed, entity_changes),
        "summary": {
            "unchanged": unchanged_count,
            "modified": modified_count,
            "added": len(added),
            "removed": len(removed),
            "ambiguous": len(ambiguous),
            "automatic_id_retention_allowed": len(ambiguous) == 0,
        },
    }
    return impact, rewrite_new_draft(new_data, mapping)


def write_json(data: dict[str, Any], path: str | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_draft", help="Old normalized screenplay JSON")
    parser.add_argument("new_draft", help="New normalized screenplay JSON")
    parser.add_argument("--output", help="Draft-impact JSON; default is stdout")
    parser.add_argument(
        "--retained-draft-output",
        help="Optional rewritten new draft with retained/allocated stable scene IDs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        old_data = load_json(args.old_draft)
        new_data = load_json(args.new_draft)
        impact, retained = compare_drafts(old_data, new_data)
        write_json(impact, args.output)
        if args.retained_draft_output:
            write_json(retained, args.retained_draft_output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
