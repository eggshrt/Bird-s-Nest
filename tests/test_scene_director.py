from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/skill-orchestrator/skills/screenplay-scene-daoyanzu/scripts/scene_director.py"
SPEC = importlib.util.spec_from_file_location("scene_director_test", SCRIPT)
director = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(director)


def breakdown() -> dict:
    return {"schema_version": "1.0.0", "project": {"id": "p"}, "source_manifest": {"sha256": "a" * 64}, "scenes": [{"id": "scn-001"}], "beats": [{"id": "bea-001", "scene_id": "scn-001", "source_refs": ["L1-L2"]}]}


def requirement(value: dict) -> dict:
    return {"schema_version": "SceneDirectionRequirementV1", "requirement_id": "r", "project_id": "p", "screenplay_hash": "a" * 64, "breakdown_hash": director.hash_json(value), "scene_ids": ["scn-001"], "production_scene_map": {"scn-001": "E001S001"}, "shot_numbering": {"pattern": "{production_scene_code}C{sequence:03d}", "reset_per_scene": True}, "goal": "direct", "audience": ["director"], "collaboration_context": {"schema_version": "CollaborationContextV1", "shared_known": [], "user_context_gaps": [], "agent_added_context": [], "joint_unknown_hypotheses": []}, "constraints": [], "active_roles": sorted(director.PERMANENT_ROLES), "acceptance_criteria": ["valid"], "initial_confirmation": {"status": "confirmed", "confirmed_at": "2026-01-01T00:00:00Z"}}


def shot() -> dict:
    value = {field: "x" for field in director.SHOT_FIELDS}
    value.update({"shot_id": "E001S001C001", "scene_id": "scn-001", "production_scene_code": "E001S001", "beat_ids": ["bea-001"], "evidence_refs": ["L1-L2"], "duration_seconds": 2})
    return value


def package() -> tuple[dict, dict]:
    b = breakdown()
    p = {"schema_version": "SceneDirectionPackageV1", "package_id": "pkg", "version": "v1", "status": "draft", "requirement": requirement(b), "chief_direction": {}, "scenes": [{"scene_id": "scn-001", "production_scene_code": "E001S001", "title": "one", "dramatic_function": "change", "beats": [], "performance_blocking": {}, "department_plans": {}, "shots": [shot()], "continuity": {}, "execution_risks": [], "source_text": "text"}], "bridge": None, "decision_log": [], "source_trace": [], "final_confirmation": {"status": "confirmed", "confirmed_at": "2026-01-01T00:00:00Z"}, "integrity": {"canonical_json_sha256": None}}
    return b, director.seal_package(p)


class SceneDirectorTests(unittest.TestCase):
    def test_rejects_zero_or_three_scenes(self) -> None:
        b = breakdown(); r = requirement(b)
        r["scene_ids"] = []
        self.assertIn("scene_ids must contain 1 or 2 scenes", director.validate_requirement(r, b))
        r["scene_ids"] = ["scn-001", "scn-002", "scn-003"]
        self.assertIn("scene_ids must contain 1 or 2 scenes", director.validate_requirement(r, b))

    def test_first_grill_blocks_requirement(self) -> None:
        b = breakdown(); r = requirement(b); r["initial_confirmation"] = {"status": "pending"}
        self.assertTrue(any("first Grill" in error for error in director.validate_requirement(r, b)))

    def test_shot_number_resets_and_references_are_checked(self) -> None:
        b, p = package(); p["scenes"][0]["shots"][0]["shot_id"] = "E001S001C002"; p["status"] = "draft"
        self.assertTrue(any("start at 001" in error for error in director.validate_package(p, b)))

    def test_seal_requires_resolved_decisions_and_hash(self) -> None:
        b, p = package()
        self.assertEqual(director.validate_package(p, b), [])
        p["decision_log"] = [{"decision_id": "d", "status": "open", "rebuttal_count": 0}]
        p["integrity"]["canonical_json_sha256"] = director.package_digest(p)
        self.assertTrue(any("unresolved" in error for error in director.validate_package(p, b)))

    def test_materializers_embed_same_hash_and_open(self) -> None:
        b, p = package(); self.assertEqual(director.validate_package(p, b), [])
        with tempfile.TemporaryDirectory() as temp:
            docx = Path(temp) / "a.docx"; xlsx = Path(temp) / "a.xlsx"
            director.render_docx(p, docx); director.render_xlsx(p, xlsx)
            for path in (docx, xlsx):
                self.assertTrue(zipfile.is_zipfile(path))
                with zipfile.ZipFile(path) as archive:
                    self.assertIn(p["integrity"]["canonical_json_sha256"], archive.read("docProps/core.xml").decode())

    def test_forbidden_outputs_are_rejected(self) -> None:
        b, p = package(); p["prompt"] = "forbidden"; p["status"] = "draft"
        self.assertTrue(any("forbidden field" in error for error in director.validate_package(p, b)))

    def test_optional_subshots_must_be_contiguous_and_bound_to_evidence(self) -> None:
        b, p = package()
        p["status"] = "draft"
        p["scenes"][0]["shots"][0]["shot_segments"] = [
            {
                "segment_id": "E001S001C001-1", "beat_ids": ["bea-001"],
                "evidence_refs": ["L1-L2"], "framing": "中景", "angle": "平视",
                "camera_position": "门外向内", "movement": "固定",
                "subject_action": "人物进门", "performance_target": "步伐急促",
                "dialogue": "", "sound": "脚步声", "last_state": "人物站定",
            },
            {
                "segment_id": "E001S001C001-2", "beat_ids": ["bea-001"],
                "evidence_refs": ["L1-L2"], "framing": "近景", "angle": "平视",
                "camera_position": "人物肩后", "movement": "缓推",
                "subject_action": "对方抬眼", "performance_target": "呼吸收紧",
                "dialogue": "一句对白", "sound": "衣料声", "last_state": "两人对视",
            },
        ]
        p = director.seal_package(p)
        self.assertEqual(director.validate_package(p, b), [])
        p["status"] = "draft"
        p["scenes"][0]["shots"][0]["shot_segments"][1]["segment_id"] = "E001S001C001-3"
        self.assertTrue(any("subshots must start at -1" in error for error in director.validate_package(p, b)))

    def test_cli_materialize_allows_docx_without_xlsx(self) -> None:
        b, p = package()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_path = root / "package.json"
            breakdown_path = root / "breakdown.json"
            docx_path = root / "director.docx"
            package_path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
            breakdown_path.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "materialize", str(package_path), "--docx", str(docx_path), "--breakdown", str(breakdown_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(docx_path.exists())
            self.assertFalse((root / "director.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
