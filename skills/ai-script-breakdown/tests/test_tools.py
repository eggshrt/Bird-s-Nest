from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


normalize = load_module("normalize_screenplay", SKILL_ROOT / "scripts" / "normalize_screenplay.py")
compare = load_module("compare_drafts", SKILL_ROOT / "scripts" / "compare_drafts.py")
validate = load_module("validate_breakdown", SKILL_ROOT / "scripts" / "validate_breakdown.py")


class NormalizeTests(unittest.TestCase):
    def test_fountain_scene_map_and_entities(self):
        text = (FIXTURES / "sample.fountain").read_text(encoding="utf-8")
        data = normalize.normalize_screenplay(text, "fountain", "src-sample", "draft-1")
        self.assertEqual(2, len(data["scenes"]))
        self.assertEqual("1", data["scenes"][0]["scene_number"])
        self.assertEqual("2", data["scenes"][1]["scene_number"])
        self.assertEqual("good", data["source_manifest"]["extraction_quality"])
        self.assertTrue(data["scenes"][0]["source_refs"][0].startswith("L1-"))
        self.assertEqual({"林岚", "周野"}, {item["name"] for item in data["characters"]})

    def test_fdx_paragraph_references(self):
        text = (FIXTURES / "sample.fdx").read_text(encoding="utf-8")
        data = normalize.normalize_screenplay(text, "fdx", "src-fdx", "draft-1")
        self.assertEqual(2, len(data["scenes"]))
        self.assertEqual("fdx_paragraph", data["source_manifest"]["reference_scheme"])
        self.assertEqual(["P1-P4"], data["scenes"][0]["source_refs"])
        self.assertEqual("顾闻", data["characters"][0]["name"])

    def test_plain_text_without_heading_is_conservative(self):
        data = normalize.normalize_screenplay("一个人站在雨里。\n他没有移动。", "text", "src-text", "draft-1")
        self.assertEqual(1, len(data["scenes"]))
        self.assertEqual("inferred", data["scenes"][0]["certainty"])
        self.assertEqual("degraded", data["source_manifest"]["extraction_quality"])
        self.assertIn("inferred_single_scene", data["source_manifest"]["warnings"])

    def test_pdf_and_docx_require_document_route(self):
        with self.assertRaises(normalize.RoutedFormatError):
            normalize.detect_format("script.pdf", None)
        with self.assertRaises(normalize.RoutedFormatError):
            normalize.detect_format("script.docx", None)

    def test_empty_extraction_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize.normalize_screenplay("\n\n", "text", "src-empty", "draft-1")


class CompareTests(unittest.TestCase):
    def test_revision_preserves_ids_and_adds_new_scene(self):
        old_text = (FIXTURES / "sample.fountain").read_text(encoding="utf-8")
        new_text = (FIXTURES / "sample_revision.fountain").read_text(encoding="utf-8")
        old = normalize.normalize_screenplay(old_text, "fountain", "src", "draft-1")
        new = normalize.normalize_screenplay(new_text, "fountain", "src", "draft-2")
        impact, retained = compare.compare_drafts(old, new)
        self.assertEqual(2, len(impact["matches"]))
        self.assertEqual(1, impact["summary"]["modified"])
        self.assertEqual(1, impact["summary"]["unchanged"])
        self.assertEqual(1, impact["summary"]["added"])
        self.assertEqual(0, impact["summary"]["removed"])
        self.assertEqual([], impact["ambiguous_matches"])
        self.assertEqual(["scn-001", "scn-003", "scn-002"], [scene["id"] for scene in retained["scenes"]])
        self.assertTrue(impact["role_impacts"])

    def test_ambiguous_match_is_not_reported_as_added_or_removed(self):
        def draft(draft_id, scenes):
            return {
                "source_manifest": {
                    "source_id": "src",
                    "draft_id": draft_id,
                    "sha256": ("a" if draft_id == "old" else "b") * 64,
                },
                "scenes": scenes,
                "characters": [],
                "locations": [],
                "props": [],
                "effects": [],
            }

        old = draft(
            "old",
            [
                {"id": "scn-001", "heading": "INT. ROOM - DAY", "text": "A opens the red door.", "source_refs": ["L1"]},
                {"id": "scn-002", "heading": "INT. ROOM - DAY", "text": "A opens the blue door.", "source_refs": ["L2"]},
            ],
        )
        new = draft(
            "new",
            [{"id": "scn-001", "heading": "INT. ROOM - DAY", "text": "A opens the door.", "source_refs": ["L1"]}],
        )
        impact, _ = compare.compare_drafts(old, new)
        self.assertEqual(1, impact["summary"]["ambiguous"])
        self.assertEqual([], impact["added_scenes"])
        self.assertEqual([], impact["removed_scenes"])
        self.assertFalse(impact["summary"]["automatic_id_retention_allowed"])


def minimal_breakdown() -> dict:
    finding = {
        "id": "fnd-001",
        "role_id": "director",
        "source_refs": ["L1-L4"],
        "scene_ids": ["scn-001"],
        "beat_ids": ["bea-001"],
        "certainty": "inferred",
        "confidence": "high",
        "severity": "medium",
        "observation": "The tactic does not change after the refusal.",
        "impact": "The beat remains dramatically static.",
        "recommendation": "Introduce a supported tactic change before the exit state.",
        "theory_refs": ["TH-MCKEE-VALUE-CHANGE"],
    }
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": "project-test",
            "title": "测试项目",
            "format": "short",
            "production_model": "fully_ai_photoreal_live_action",
        },
        "source_manifest": {
            "source_id": "source-test",
            "draft_id": "draft-1",
            "format": "fountain",
            "sha256": "a" * 64,
            "character_count": 30,
            "extraction_quality": "good",
            "warnings": [],
        },
        "coverage": {
            "status": "completed",
            "requested_scene_ids": ["scn-001"],
            "completed_scene_ids": ["scn-001"],
            "pending_scene_ids": [],
            "requested_role_ids": ["director"],
            "completed_role_ids": ["director"],
            "pending_role_ids": [],
            "ai_baseline_completed": True,
            "cross_role_synthesis_completed": True,
            "current_batch": None,
            "continuation_anchor": None,
        },
        "global_analysis": {
            "story_contract": {},
            "narrative_form": {},
            "causal_spine": [],
            "character_system": {},
            "information_design": {},
            "theme_values": {},
            "setup_payoff": [],
            "world_rules": [],
            "rhythm": {},
            "continuity": {},
        },
        "entities": {"characters": [], "locations": [], "props": [], "effects": []},
        "scenes": [
            {
                "id": "scn-001",
                "heading": "INT. ROOM - NIGHT",
                "source_refs": ["L1-L4"],
                "certainty": "explicit",
                "entry_state": {},
                "exit_state": {},
                "summary": "A refusal leaves the tactic unchanged.",
            }
        ],
        "beats": [
            {
                "id": "bea-001",
                "scene_id": "scn-001",
                "source_refs": ["L2-L4"],
                "change": "The request is refused.",
                "entry_state": {},
                "exit_state": {},
            }
        ],
        "ai_feasibility": {
            "asset_locks": [],
            "continuity_requirements": [],
            "complexity_flags": [],
            "reference_requirements": [],
            "duration_pressure": [],
            "audio_dependencies": [],
            "risks": [],
            "fallbacks": [],
            "blockers": [],
        },
        "role_reports": [
            {
                "role_id": "director",
                "display_name": "导演",
                "status": "completed",
                "contract": {},
                "findings": [copy.deepcopy(finding)],
                "deliverables": {},
                "dependencies": [],
                "blockers": [],
            }
        ],
        "issues": [finding],
        "cross_role_decisions": [],
        "theory_trace": [
            {
                "theory_id": "TH-MCKEE-VALUE-CHANGE",
                "applied_to": ["fnd-001"],
                "reason": "The beat is tested for meaningful value movement.",
            }
        ],
        "handoff": {"artifacts": ["breakdown.md", "breakdown.json"], "ready_for": [], "blocked_by": []},
    }


class ValidateTests(unittest.TestCase):
    def test_valid_breakdown_and_markdown(self):
        data = minimal_breakdown()
        markdown = "项目 project-test\n场景 scn-001\n问题 fnd-001\n岗位 导演\n"
        result = validate.validate_breakdown(data, markdown)
        self.assertEqual([], result.errors)

    def test_completed_coverage_rejects_pending(self):
        data = minimal_breakdown()
        data["coverage"]["pending_scene_ids"] = ["scn-001"]
        result = validate.validate_breakdown(data)
        self.assertTrue(any("pending" in error for error in result.errors))

    def test_partial_coverage_with_anchor_is_valid(self):
        data = minimal_breakdown()
        data["coverage"].update(
            {
                "status": "partial",
                "completed_scene_ids": [],
                "pending_scene_ids": ["scn-001"],
                "completed_role_ids": [],
                "pending_role_ids": ["director"],
                "ai_baseline_completed": False,
                "cross_role_synthesis_completed": False,
                "current_batch": "batch-001",
                "continuation_anchor": "▶ CONTINUE FROM: scn-001 房间",
            }
        )
        result = validate.validate_breakdown(data)
        self.assertEqual([], result.errors)

    def test_custom_role_requires_confirmation(self):
        data = minimal_breakdown()
        data["coverage"]["requested_role_ids"] = ["role-action-designer"]
        data["coverage"]["completed_role_ids"] = ["role-action-designer"]
        report = data["role_reports"][0]
        report["role_id"] = "role-action-designer"
        report["display_name"] = "动作设计"
        report["contract"] = {"confirmed": False}
        report["findings"][0]["role_id"] = "role-action-designer"
        data["issues"][0]["role_id"] = "role-action-designer"
        result = validate.validate_breakdown(data)
        self.assertTrue(any("confirmed contract" in error for error in result.errors))

    def test_storyboard_rejects_prompt_fields(self):
        data = minimal_breakdown()
        data["coverage"]["requested_role_ids"] = ["storyboard"]
        data["coverage"]["completed_role_ids"] = ["storyboard"]
        report = data["role_reports"][0]
        report["role_id"] = "storyboard"
        report["display_name"] = "分镜"
        report["findings"][0]["role_id"] = "storyboard"
        data["issues"][0]["role_id"] = "storyboard"
        report["deliverables"] = {"generation_prompt": "forbidden"}
        result = validate.validate_breakdown(data)
        self.assertTrue(any("forbidden prompt" in error for error in result.errors))

    def test_schemas_are_valid_json(self):
        for path in sorted((SKILL_ROOT / "schemas").glob("*.json")):
            with self.subTest(path=path.name):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_skill_entry_has_no_scaffold_and_is_explicit_only(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        yaml_text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertNotIn("[" + "TODO:", skill_text)
        self.assertIn("allow_implicit_invocation: false", yaml_text)
        self.assertIn("Two-stage gate", skill_text)


if __name__ == "__main__":
    unittest.main()
