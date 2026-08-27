from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO / "plugins" / "skill-orchestrator" / "skills" / "screenplay-concept-director"
SCRIPT = SKILL_ROOT / "scripts" / "concept_director.py"
SPEC = importlib.util.spec_from_file_location("concept_director", SCRIPT)
director = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(director)


def completed_role(role_id: str, index: int) -> dict:
    return {
        "role_id": role_id,
        "display_name": role_id,
        "status": "completed",
        "contract": {},
        "findings": [{
            "id": f"fnd-{index:03d}",
            "role_id": role_id,
            "source_refs": ["L1-L4"],
            "scene_ids": ["scn-001"],
            "beat_ids": ["bea-001"],
            "certainty": "explicit",
            "confidence": "high",
            "severity": "medium",
            "observation": "林夏在压力下仍先整理工具。",
            "impact": "行为需要转译为外显设计。",
            "recommendation": "保留清晰的维护与使用痕迹。",
            "theory_refs": [],
        }],
        "deliverables": {"visual_basis": "克制、可生产、行为驱动"},
        "dependencies": [],
        "blockers": [],
    }


def sample_breakdown() -> dict:
    roles = ["chief_director", "director", "performance_execution", "art"]
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": "bird-nest",
            "title": "归巢",
            "format": "short",
            "production_model": "fully_ai_photoreal_live_action",
            "aspect_ratio": "2.39:1",
        },
        "source_manifest": {
            "source_id": "src-001",
            "draft_id": "draft-1",
            "format": "fountain",
            "sha256": "a" * 64,
            "character_count": 100,
            "extraction_quality": "good",
            "warnings": [],
        },
        "coverage": {
            "status": "completed",
            "requested_scene_ids": ["scn-001"],
            "completed_scene_ids": ["scn-001"],
            "pending_scene_ids": [],
            "requested_role_ids": roles,
            "completed_role_ids": roles,
            "pending_role_ids": [],
            "ai_baseline_completed": True,
            "cross_role_synthesis_completed": True,
            "current_batch": None,
            "continuation_anchor": None,
        },
        "global_analysis": {
            "story_contract": {"promise": "回家不是回到原点"},
            "narrative_form": {"mode": "linear"},
            "causal_spine": [],
            "character_system": {"protagonist": "chr-001"},
            "information_design": {},
            "theme_values": {"axis": "控制/信任"},
            "setup_payoff": [],
            "world_rules": [{"id": "wr-001", "rule": "修补优先于替换"}],
            "rhythm": {},
            "continuity": {"invariant": "雨夜"},
        },
        "entities": {
            "characters": [{
                "id": "chr-001", "name": "林夏", "aliases": ["小夏"],
                "source_refs": ["L1-L4"], "scene_ids": ["scn-001"], "certainty": "explicit",
                "states": [{"state_id": "canonical", "label": "返乡状态", "source_refs": ["L1-L4"]}],
            }],
            "locations": [{
                "id": "loc-001", "name": "江边修理厂", "aliases": ["修理厂"],
                "source_refs": ["L1-L8"], "scene_ids": ["scn-001"], "certainty": "explicit",
            }],
            "props": [{
                "id": "prp-001", "name": "铜钥匙", "aliases": ["钥匙"],
                "source_refs": ["L3-L4"], "scene_ids": ["scn-001"], "certainty": "explicit",
                "states": ["intact", "bent"],
            }],
            "effects": [],
        },
        "scenes": [{
            "id": "scn-001", "heading": "内景 江边修理厂 夜", "source_refs": ["L1-L8"],
            "certainty": "explicit", "entry_state": {}, "exit_state": {},
            "summary": "林夏在雨夜回到修理厂，用铜钥匙开门。",
        }],
        "beats": [{
            "id": "bea-001", "scene_id": "scn-001", "source_refs": ["L3-L4"],
            "change": "林夏决定开门", "entry_state": {}, "exit_state": {},
        }],
        "ai_feasibility": {
            "asset_locks": [], "continuity_requirements": [], "complexity_flags": [],
            "reference_requirements": [], "duration_pressure": [], "audio_dependencies": [],
            "risks": [], "fallbacks": [], "blockers": [],
        },
        "role_reports": [completed_role(role, index + 1) for index, role in enumerate(roles)],
        "issues": [],
        "cross_role_decisions": [],
        "theory_trace": [],
        "handoff": {"artifacts": [], "ready_for": [], "blocked_by": []},
    }


def valid_dimensions(asset_type: str) -> dict:
    return {
        "shared": {key: f"observable {key}" for key in sorted(director.REQUIRED_SHARED_DIMENSIONS)},
        "type_specific": {key: f"observable {key}" for key in sorted(director.REQUIRED_TYPE_DIMENSIONS[asset_type])},
    }


def valid_position(asset_id: str) -> dict:
    return {
        "schema_version": "CreativePositionV1",
        "asset_id": asset_id,
        "claim": "用被反复维护的克制轮廓外显人物控制欲。",
        "evidence": ["L1-L4：她在压力下先整理工具。"],
        "aesthetic_preference": "反对用夸张饰品替代行为设计。",
        "objections": ["俗套符号会削弱可信度。"],
        "alternative": "若表演节奏改变，可减少服装层级并强化动作线。",
        "risks": ["过度磨损会误读为贫困。"],
        "confidence": "high",
        "change_conditions": ["新稿明确她刻意追求华丽时改变观点。"],
        "decision_owner": "user",
        "human_statement": "我推荐克制、维护良好的轮廓；它比装饰性符号更忠于她的行为。",
    }


def valid_requirement(snapshot: dict) -> dict:
    asset = snapshot["asset"]
    asset_id = asset["asset_id"]
    return {
        "schema_version": "VisualAssetRequirementV1",
        "version": "v1",
        "baseline_ref": {
            "project_id": snapshot["project"]["id"],
            "draft_id": snapshot["draft_id"],
            "source_hash": snapshot["source_hash"],
            "breakdown_hash": snapshot["breakdown_hash"],
            "analyzer_hash": snapshot["analyzer_hash"],
            "context_hash": snapshot["context_hash"],
        },
        "asset": {"asset_id": asset_id, "asset_type": asset["asset_type"], "name": asset["name"]},
        "primary_state": {
            "state_id": "canonical", "asset_id": asset_id, "label": "返乡状态",
            "design_direction": "克制、维护良好、以行为痕迹代替装饰符号。",
            "design_language": ["窄而稳定的垂直结构", "所有磨损都有操作来源"],
            "concrete_elements": ["袖口有规律的修补", "重量落在前脚掌"],
        },
        "derived_states": [{
            "state_id": "post-conflict", "asset_id": asset_id, "label": "冲突后",
            "delta_from": "canonical", "changes": ["右袖新增不规则撕裂"], "source_refs": ["L7-L8"],
        }],
        "design_dimensions": valid_dimensions(asset["asset_type"]),
        "evidence": [
            {"kind": "fact", "statement": "林夏先整理工具。", "source_refs": ["L1-L4"]},
            {"kind": "design_decision", "statement": "用规律修补表现控制感。", "source_refs": []},
            {"kind": "preference", "statement": "避免装饰性符号堆叠。", "source_refs": []},
        ],
        "high_impact_decisions": [{
            "id": "dec-001", "topic": "整体方向", "chosen_option": "行为驱动的克制设计",
            "status": "accepted", "consequence": "需要清晰维护痕迹",
        }],
        "reference_images": [],
        "production_constraints": ["真人影视可实现，保持服装层级不超过三层"],
        "cultural_boundaries": ["不使用无来源的地域祭祀符号"],
        "invariants": ["规律修补", "前倾但克制的动作线"],
        "exclusions": ["无剧情依据的奢华饰品"],
        "acceptance_criteria": [{
            "id": "AC-1", "criterion": "静止剪影可读出克制前倾的动作线", "method": "轮廓评审",
        }],
        "open_questions": [],
        "confirmations": [
            {"gate": "asset_selection", "confirmed": True, "confirmed_at": "2026-08-27T01:00:00Z"},
            {"gate": "design_requirement", "confirmed": True, "confirmed_at": "2026-08-27T01:05:00Z"},
            {"gate": "persistence_plan", "confirmed": True, "confirmed_at": "2026-08-27T01:10:00Z"},
        ],
    }


class ConceptDirectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.analyzer = self.base / "analyzer"
        self.analyzer.mkdir()
        (self.analyzer / "SKILL.md").write_text("analyzer-v1\n", encoding="utf-8")
        self.breakdown = sample_breakdown()
        self.catalog = director.build_catalog(self.breakdown, self.analyzer)
        self.snapshot = director.build_snapshot(
            self.breakdown, self.catalog, "chr-001", created_at="2026-08-27T00:00:00Z", analyzer_root=self.analyzer
        )
        self.requirement = valid_requirement(self.snapshot)
        self.position = valid_position("chr-001")

    def test_catalog_maps_four_types_and_stable_ids(self) -> None:
        by_id = {item["asset_id"]: item["asset_type"] for item in self.catalog["assets"]}
        self.assertEqual(by_id, {
            "chr-001": "character_master", "loc-001": "location_master",
            "prp-001": "hero_prop", "scn-001": "scene_state",
        })
        again = director.build_catalog(deepcopy(self.breakdown), self.analyzer)
        self.assertEqual(self.catalog["assets"], again["assets"])
        self.assertEqual(self.catalog["breakdown_hash"], again["breakdown_hash"])

    def test_duplicate_name_is_ambiguous_and_never_auto_confirms(self) -> None:
        payload = deepcopy(self.breakdown)
        payload["entities"]["props"][0]["name"] = "林夏"
        catalog = director.build_catalog(payload, self.analyzer)
        ambiguity = next(item for item in catalog["ambiguities"] if item["normalized_name"] == "林夏")
        self.assertEqual(ambiguity["asset_ids"], ["chr-001", "prp-001"])
        resolved = director.resolve_asset(catalog, "林夏")
        self.assertIsNone(resolved["recommended_asset_id"])
        self.assertTrue(resolved["confirmation_required"])

    def test_name_resolution_reports_stable_id_and_evidence(self) -> None:
        resolved = director.resolve_asset(self.catalog, "小夏")
        self.assertEqual(resolved["recommended_asset_id"], "chr-001")
        self.assertEqual(resolved["candidates"][0]["source_refs"], ["L1-L4"])
        self.assertTrue(resolved["confirmation_required"])

    def test_freshness_detects_coverage_source_and_analyzer_change(self) -> None:
        incomplete = deepcopy(self.breakdown)
        incomplete["coverage"]["pending_role_ids"] = ["art"]
        report = director.freshness_report(incomplete, self.catalog, analyzer_root=self.analyzer)
        self.assertIn("pending_roles", report["reasons"])
        source = self.base / "changed.fountain"
        source.write_text("INT. DIFFERENT ROOM - DAY\n", encoding="utf-8")
        report = director.freshness_report(self.breakdown, self.catalog, source=source, analyzer_root=self.analyzer)
        self.assertIn("source_hash_changed", report["reasons"])
        (self.analyzer / "SKILL.md").write_text("analyzer-v2\n", encoding="utf-8")
        report = director.freshness_report(self.breakdown, self.catalog, analyzer_root=self.analyzer)
        self.assertIn("analyzer_hash_changed", report["reasons"])

    def test_snapshot_is_disk_derived_bounded_and_deterministic(self) -> None:
        first = director.build_snapshot(self.breakdown, self.catalog, "chr-001", created_at="2026-01-01T00:00:00Z", analyzer_root=self.analyzer)
        second = director.build_snapshot(self.breakdown, self.catalog, "chr-001", created_at="2027-01-01T00:00:00Z", analyzer_root=self.analyzer)
        self.assertEqual(first["context_hash"], second["context_hash"])
        self.assertFalse(first["inclusion"]["full_screenplay_included"])
        bounded = director.build_snapshot(self.breakdown, self.catalog, "chr-001", analyzer_root=self.analyzer, max_scenes=0, max_beats=0, max_findings=0)
        self.assertEqual(bounded["relevant_scenes"], [])
        self.assertEqual(bounded["inclusion"]["omitted_scene_ids"], ["scn-001"])

    def test_valid_requirement_and_position_pass(self) -> None:
        self.assertEqual(director.validate_requirement(self.requirement, self.snapshot, self.position), [])

    def test_all_four_asset_contracts_validate(self) -> None:
        for asset_id in ("chr-001", "loc-001", "scn-001", "prp-001"):
            with self.subTest(asset_id=asset_id):
                snapshot = director.build_snapshot(
                    self.breakdown, self.catalog, asset_id, analyzer_root=self.analyzer,
                    created_at="2026-08-27T00:00:00Z",
                )
                requirement = valid_requirement(snapshot)
                position = valid_position(asset_id)
                self.assertEqual(director.validate_requirement(requirement, snapshot, position), [])

    def test_multiple_assets_and_cross_asset_state_are_rejected(self) -> None:
        payload = deepcopy(self.requirement)
        payload["derived_states"][0]["asset_id"] = "loc-001"
        errors = director.validate_requirement(payload, self.snapshot, self.position)
        self.assertTrue(any("more than one asset_id" in error for error in errors))
        self.assertTrue(any("crosses" in error for error in errors))

    def test_derived_state_can_be_removed(self) -> None:
        payload = deepcopy(self.requirement)
        payload["derived_states"] = []
        self.assertEqual(director.validate_requirement(payload, self.snapshot, self.position), [])

    def test_missing_type_dimension_is_rejected(self) -> None:
        payload = deepcopy(self.requirement)
        del payload["design_dimensions"]["type_specific"]["growth_stage"]
        errors = director.validate_requirement(payload, self.snapshot, self.position)
        self.assertTrue(any("growth_stage" in error for error in errors))

    def test_unresolved_decision_open_question_and_missing_evidence_are_rejected(self) -> None:
        payload = deepcopy(self.requirement)
        payload["high_impact_decisions"][0]["status"] = "proposed"
        payload["open_questions"] = ["服装年代？"]
        payload["evidence"][0]["source_refs"] = []
        payload["confirmations"] = payload["confirmations"][:2]
        errors = director.validate_requirement(payload, self.snapshot, self.position)
        self.assertTrue(any("not accepted" in error for error in errors))
        self.assertTrue(any("open_questions" in error for error in errors))
        self.assertTrue(any("source_refs" in error for error in errors))
        self.assertTrue(any("three distinct" in error for error in errors))

    def test_prompt_and_non_user_reference_fields_are_rejected(self) -> None:
        payload = deepcopy(self.requirement)
        payload["generation_prompt"] = "forbidden"
        payload["reference_images"] = [{"source": "web", "controls": ["palette"], "must_not_control": ["identity"]}]
        errors = director.validate_requirement(payload, self.snapshot, self.position)
        self.assertTrue(any("forbidden" in error for error in errors))
        self.assertTrue(any("user_provided" in error for error in errors))
        position = deepcopy(self.position)
        position["negative_prompt"] = "forbidden"
        self.assertTrue(any("prompt" in error for error in director.validate_position(position, "chr-001")))

    def test_stale_or_mismatched_snapshot_is_rejected(self) -> None:
        stale = deepcopy(self.snapshot)
        stale["freshness"]["status"] = "stale"
        payload = deepcopy(self.requirement)
        payload["baseline_ref"]["source_hash"] = "b" * 64
        errors = director.validate_requirement(payload, stale, self.position)
        self.assertIn("snapshot is stale", errors)
        self.assertTrue(any("baseline_ref.source_hash" in error for error in errors))

    def test_corrupt_snapshot_hash_and_catalog_mismatch_are_rejected(self) -> None:
        snapshot = deepcopy(self.snapshot)
        snapshot["global_visual_context"]["story_contract"] = {"tampered": True}
        errors = director.validate_requirement(self.requirement, snapshot, self.position)
        self.assertTrue(any("context_hash" in error for error in errors))
        catalog = deepcopy(self.catalog)
        catalog["source_hash"] = "b" * 64
        self.assertTrue(any("source_hash" in error for error in director.validate_catalog_snapshot(catalog, self.snapshot)))

    def test_materialize_writes_only_contract_artifacts_and_never_overwrites(self) -> None:
        output = self.base / "outputs"
        report = director.materialize(self.catalog, self.snapshot, self.requirement, self.position, output)
        self.assertEqual(report["status"], "succeeded")
        version_dir = output / "bird-nest" / "draft-1" / "assets" / "chr-001" / "v1"
        self.assertEqual(
            sorted(path.name for path in version_dir.iterdir()),
            ["context-snapshot.json", "creative-position.json", "decision-log.md", "requirement.json", "requirement.md"],
        )
        serialized = "\n".join(path.read_text(encoding="utf-8") for path in version_dir.iterdir())
        for forbidden in ("negative_prompt", "generation_prompt", "model_parameter", "image_generation"):
            self.assertNotIn(forbidden, serialized)
        with self.assertRaisesRegex(ValueError, "already exists"):
            director.materialize(self.catalog, self.snapshot, self.requirement, self.position, output)


class ContractAndBehaviorTests(unittest.TestCase):
    def test_skill_is_explicit_plan_gated_three_gate_and_no_subagents(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        ui = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
        self.assertIn("explicitly invoked `$screenplay-concept-director`", skill)
        self.assertIn("请切换到 Plan Mode 后重新调用", skill)
        self.assertIn("three distinct confirmations", skill)
        self.assertIn("Never use conversational memory as project truth", skill)
        self.assertIn("Do not invoke subagents unless the user explicitly authorizes", skill)
        self.assertIn("Do not search the web for references unless", workflow)
        self.assertIn("Do not complete the interview while any consequential creative choice remains unresolved", skill)
        self.assertIn("allow_implicit_invocation: false", ui)

    def test_persona_requires_one_position_and_user_override(self) -> None:
        persona = (SKILL_ROOT / "references" / "persona-and-debate.md").read_text(encoding="utf-8")
        self.assertIn("one preferred direction", persona)
        self.assertIn("The user owns the final aesthetic decision", persona)
        self.assertIn("fact", persona)
        self.assertIn("unknown", persona)

    def test_ai_script_breakdown_matches_lock_and_canonical_copy(self) -> None:
        bundled = REPO / "plugins" / "skill-orchestrator" / "skills" / "ai-script-breakdown"
        lock = json.loads((REPO / "plugins" / "skill-orchestrator" / "locks" / "ai-script-breakdown.lock.json").read_text())
        actual = {}
        for path in sorted(bundled.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
                actual[str(path.relative_to(bundled))] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(actual, lock["files"])
        canonical = Path.home() / ".codex" / "skills" / "ai-script-breakdown"
        if canonical.is_dir():
            for relative, digest in lock["files"].items():
                self.assertEqual(hashlib.sha256((canonical / relative).read_bytes()).hexdigest(), digest)

    def test_grill_gold_has_five_cases_per_asset_type(self) -> None:
        payload = json.loads((REPO / "evals" / "concept-grill-gold.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(payload["cases"]), 20)
        counts = {}
        for case in payload["cases"]:
            counts[case["asset_type"]] = counts.get(case["asset_type"], 0) + 1
            self.assertGreaterEqual(len(case["expected_dimensions"]), 2)
            self.assertIn("single_recommendation", case["expected_behavior"])
            self.assertIn("observable_requirements", case["expected_behavior"])
        self.assertEqual(counts, {
            "character_master": 5, "location_master": 5, "scene_state": 5, "hero_prop": 5,
        })


if __name__ == "__main__":
    unittest.main()
