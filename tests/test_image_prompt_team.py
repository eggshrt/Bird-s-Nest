from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins" / "skill-orchestrator" / "skills" / "image-prompt-team" / "scripts" / "image_prompt_team.py"
SPEC = importlib.util.spec_from_file_location("image_prompt_team_test", SCRIPT)
team = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(team)


def requirement(asset_type: str = "character_master", asset_id: str = "chr-001", name: str = "林夏") -> dict:
    return {
        "schema_version": "VisualAssetRequirementV1", "version": "v2",
        "baseline_ref": {"project_id": "bird-nest", "draft_id": "draft-1", "source_hash": "a" * 64, "breakdown_hash": "b" * 64},
        "asset": {"asset_id": asset_id, "asset_type": asset_type, "name": name},
        "primary_state": {"state_id": "canonical", "asset_id": asset_id, "label": "母版", "design_direction": "以可靠克制和精确整理建立可观察方向", "design_language": ["修长窄直的垂直骨架", "所有磨损都有长期操作来源"], "concrete_elements": ["齐颈双耳后收发型与双层矮立领形成窄V负形", "靛灰旧棉斜纹及胯外套", "右袖低对比规律针脚"]},
        "derived_states": [],
        "design_dimensions": {"shared": {"dramatic_function": "首先读出可靠、克制、整理准确", "target_perception": "能力可信但不冷硬", "frame": "全身人物母版", "production_limits": "全部结构可真实制作"}, "type_specific": {"body_proportion": "四肢偏长，肩线不过宽", "posture_action_line": "中性站姿，重心轻落前脚掌", "clothing_layers": "靛灰外套与暖灰内层"}},
        "evidence": [{"kind": "fact", "statement": "林夏在压力下仍先整理工具。", "source_refs": ["L1-L4"]}, {"kind": "design_decision", "statement": "用领发负形作为第一识别。", "source_refs": []}],
        "high_impact_decisions": [{"id": "D1", "topic": "方向", "chosen_option": "克制可靠", "status": "accepted", "consequence": "不新增状态"}],
        "reference_images": [], "production_constraints": ["真人影视可制作"], "cultural_boundaries": ["不添加无来源文化符号"],
        "invariants": ["窄V负形", "修长窄直轮廓"], "exclusions": ["可见铜钥匙", "临时雨水", "贫困化做旧", "第二资产"],
        "acceptance_criteria": [{"id": "AC-1", "criterion": "全身可读", "method": "盲读"}], "open_questions": [],
        "confirmations": [{"gate": "asset_selection", "confirmed": True}, {"gate": "design_requirement", "confirmed": True}, {"gate": "persistence_plan", "confirmed": True}],
    }


class ImagePromptTeamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup); self.base = Path(self.temporary.name)

    def write_requirement(self, payload: dict | None = None) -> Path:
        path = self.base / "requirement.json"; path.write_text(json.dumps(payload or requirement(), ensure_ascii=False, indent=2), encoding="utf-8"); return path

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.base), *args], text=True, capture_output=True, env={**os.environ, "ORCHESTRATOR_TEST_MODE": "1"})

    def test_sealed_single_asset_validation(self) -> None:
        self.assertEqual(team.validate_visual_requirement(requirement()), [])
        payload = requirement(); payload["derived_states"] = [{"state_id": "other", "asset_id": "chr-002"}]
        self.assertTrue(any("exactly one" in error for error in team.validate_visual_requirement(payload)))
        payload = requirement(); payload["high_impact_decisions"][0]["status"] = "proposed"; payload["evidence"][0]["source_refs"] = []; payload["design_dimensions"]["shared"]["prompt"] = "forbidden"
        errors = team.validate_visual_requirement(payload)
        self.assertTrue(any("not accepted" in error for error in errors)); self.assertTrue(any("no source_refs" in error for error in errors)); self.assertTrue(any("forbidden downstream" in error for error in errors))

    def test_graph_runs_six_roles_one_type_role_and_optional_reference(self) -> None:
        payload = requirement(); graph = team.build_graph(payload); roles = {item["role_skill"] for item in graph["nodes"]}
        self.assertEqual(graph["max_concurrency"], 3); self.assertTrue(set(team.CREATIVE_ROLE_SKILLS.values()).issubset(roles)); self.assertIn("character-asset-designer", roles); self.assertNotIn("reference-role-director", roles); self.assertNotIn("prompt-architect", roles)
        payload["reference_images"] = [{"sha256": "f" * 64, "responsibility": "材质"}]
        self.assertIn("reference-role-director", {item["role_skill"] for item in team.build_graph(payload)["nodes"]})

    def test_all_v04_roles_are_dispatcher_only(self) -> None:
        names = set(team.ROLE_SKILLS.values()) | set(team.ASSET_ROLE_SKILLS.values())
        for name in names:
            root = REPO / "plugins" / "skill-orchestrator" / "skills" / name
            config = yaml.safe_load((root / "agents" / "openai.yaml").read_text(encoding="utf-8"))
            self.assertFalse(config["policy"]["allow_implicit_invocation"], name)
            body = (root / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("dispatcher-signed `AgentTaskV1`", body); self.assertIn("$image-prompt-team", body)

    def test_prompt_uses_unlabeled_paragraphs_and_official_order(self) -> None:
        prompt, constraints = team.make_prompt(requirement())
        self.assertNotRegex(prompt, r"【[^】]+】"); self.assertGreaterEqual(len(prompt.split("\n\n")), 5); self.assertLessEqual(len(constraints), 3)
        self.assertNotIn("negative_prompt", prompt); self.assertNotIn("模型参数", prompt)

    def test_visibility_blocks_invariant_hiding_framing(self) -> None:
        matrix = team.visibility_matrix(requirement(), {"intended_use": "人物母版", "framing": "面部特写", "aspect_ratio": "1:1"})
        self.assertTrue(any(item["invariant"] and not item["visible"] for item in matrix))

    def test_environment_is_pure_environment(self) -> None:
        payload = requirement("location_master", "loc-001", "旧站厅")
        spec = team.build_spec(payload, "h", team.recommend_presentation(payload), [team.expert_position(role, payload, team.recommend_presentation(payload)) for role in [*team.CREATIVE_ROLE_SKILLS.values(), "environment-asset-designer"]])
        self.assertIn("人物或人群", spec["exclusions"])

    def test_gold_has_36_case_distribution(self) -> None:
        cases = json.loads((REPO / "evals" / "prompt-gold.json").read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 36)
        self.assertEqual({key: sum(case["category"] == key for case in cases) for key in ("character", "environment", "prop")}, {"character": 16, "environment": 12, "prop": 8})
        self.assertTrue(all(case["must_include"] and case["must_not_include"] for case in cases))

    def test_plan_mode_hard_stops_without_database(self) -> None:
        source, db = self.write_requirement(), self.base / "runtime.sqlite3"
        completed = self.run_cli("--db", str(db), "run", "--requirement", str(source), "--collaboration-mode", "plan", "--confirm-initial", "--accept-presentation-recommendation", "--backend", "deterministic", "--test-mode")
        self.assertEqual(completed.returncode, 2); self.assertIn("Plan Mode", completed.stdout); self.assertFalse(db.exists())

    def test_three_confirmation_gates_and_offline_e2e(self) -> None:
        source, db = self.write_requirement(), self.base / "runtime.sqlite3"
        preview = self.run_cli("--db", str(db), "run", "--requirement", str(source), "--backend", "deterministic", "--test-mode")
        self.assertEqual(preview.returncode, 3); self.assertFalse(db.exists())

        first = self.run_cli("--db", str(db), "run", "--requirement", str(source), "--confirm-initial", "--accept-presentation-recommendation", "--backend", "deterministic", "--test-mode")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr); phase1 = json.loads(first.stdout)
        self.assertEqual(phase1["status"], "awaiting_spec_confirmation"); self.assertFalse((self.base / "outputs").exists())

        rejected_spec = self.run_cli("--db", str(db), "confirm-spec", "--run-id", phase1["run_id"], "--backend", "deterministic", "--test-mode")
        self.assertEqual(rejected_spec.returncode, 2)
        second = self.run_cli("--db", str(db), "confirm-spec", "--run-id", phase1["run_id"], "--confirm-spec", "--backend", "deterministic", "--test-mode")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr); phase2 = json.loads(second.stdout); self.assertEqual(phase2["status"], "proposed"); self.assertFalse((self.base / "outputs").exists())

        rejected_final = self.run_cli("--db", str(db), "approve", "--run-id", phase1["run_id"])
        self.assertEqual(rejected_final.returncode, 2)
        approved = self.run_cli("--db", str(db), "approve", "--run-id", phase1["run_id"], "--confirm-final")
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr); output = Path(json.loads(approved.stdout)["output"])
        self.assertEqual({item.name for item in output.iterdir()}, {"generation-prompt.txt", "visual-prompt-spec.json", "prompt-package.json", "decision-log.md", "run-report.json"})
        package = json.loads((output / "prompt-package.json").read_text(encoding="utf-8")); spec = json.loads((output / "visual-prompt-spec.json").read_text(encoding="utf-8")); self.assertEqual(package["status"], "approved"); self.assertEqual(team.validate_package(package), []); self.assertNotIn("design_statement", package); self.assertEqual(package["visual_prompt_spec_hash"], team.spec_content_hash(spec))

    def test_pre_v04_run_is_read_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "read/export-only"):
            team.require_v04({"metadata": {"plugin_version": "0.3.0"}})


if __name__ == "__main__": unittest.main()
