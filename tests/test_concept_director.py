from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from concept_fixtures import ConceptFixture, REPO, director

SKILL_ROOT = REPO / "plugins" / "skill-orchestrator" / "skills" / "screenplay-concept-director"


class ConceptDirectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.fixture = ConceptFixture(self.base)
        self.breakdown = self.fixture.breakdown
        self.catalog = self.fixture.catalog
        self.snapshot = self.fixture.snapshot
        self.requirement = self.fixture.requirement
        self.position = self.fixture.position

    def validate(self, requirement=None, snapshot=None, position=None) -> list[str]:
        return director.validate_requirement(
            requirement if requirement is not None else self.requirement,
            snapshot if snapshot is not None else self.snapshot,
            position if position is not None else self.position,
        )

    def test_catalog_maps_four_types_and_stable_ids(self) -> None:
        self.assertEqual({item["asset_id"]: item["asset_type"] for item in self.catalog["assets"]}, {
            "chr-001": "character_master", "loc-001": "location_master",
            "prp-001": "hero_prop", "scn-001": "scene_state",
        })
        self.assertEqual(self.catalog, director.build_catalog(deepcopy(self.breakdown)))

    def test_ambiguous_name_never_auto_confirms(self) -> None:
        self.breakdown["entities"]["props"][0]["name"] = "林夏"
        self.fixture.persist_baseline()
        result = director.resolve_asset(self.fixture.catalog, "林夏")
        self.assertIsNone(result["recommended_asset_id"])
        self.assertTrue(result["confirmation_required"])
        self.assertEqual({item["asset_id"] for item in result["candidates"]}, {"chr-001", "prp-001"})

    def test_name_resolution_retains_evidence(self) -> None:
        result = director.resolve_asset(self.catalog, "小夏")
        self.assertEqual(result["recommended_asset_id"], "chr-001")
        self.assertEqual(result["candidates"][0]["source_refs"], ["L1-L4"])
        self.assertTrue(result["confirmation_required"])

    def test_catalog_cannot_refresh_incomplete_or_unproven_baseline(self) -> None:
        mutations = [
            lambda b: b["source_manifest"].pop("analysis_provenance"),
            lambda b: b["coverage"].update(completed_scene_ids=[]),
            lambda b: b["coverage"].update(requested_scene_ids=[]),
            lambda b: b["coverage"].update(pending_role_ids=["art"]),
            lambda b: b["role_reports"][0].update(status="pending"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                payload = deepcopy(self.breakdown)
                mutate(payload)
                self.assertEqual(director.freshness_report(payload)["status"], "stale")
                with self.assertRaises(ValueError):
                    director.build_catalog(payload)

    def test_source_change_is_detected_without_optional_source_argument(self) -> None:
        self.fixture.source.write_text("INT. DIFFERENT ROOM - DAY\n", encoding="utf-8")
        self.assertEqual(director.freshness_report(self.breakdown)["status"], "stale")
        self.assertTrue(self.validate())
        with self.assertRaises(ValueError):
            director.build_catalog(self.breakdown)

    def test_rebuilt_catalog_cannot_launder_analyzer_change(self) -> None:
        analyzer = self.base / "analyzer"
        analyzer.mkdir()
        (analyzer / "SKILL.md").write_text("analyzer-v1\n", encoding="utf-8")
        fixture = ConceptFixture(self.base / "custom", analyzer_root=analyzer)
        (analyzer / "SKILL.md").write_text("analyzer-v2\n", encoding="utf-8")
        report = director.freshness_report(fixture.breakdown, analyzer_root=analyzer)
        self.assertEqual(report["status"], "stale")
        with self.assertRaises(ValueError):
            director.build_catalog(fixture.breakdown, analyzer)
        self.assertTrue(director.validate_requirement(fixture.requirement, fixture.snapshot, fixture.position, analyzer_root=analyzer))

    def test_snapshot_requires_exact_breakdown_on_disk(self) -> None:
        self.breakdown["global_analysis"]["story_contract"] = {"promise": "changed in memory"}
        self.fixture.catalog = director.build_catalog(self.breakdown)
        with self.assertRaises(ValueError):
            self.fixture.snapshot_for()
        self.breakdown = deepcopy(self.fixture.breakdown)
        self.fixture.breakdown_path.unlink()
        self.assertTrue(self.validate())

    def test_breakdown_change_after_confirmation_invalidates_requirement(self) -> None:
        payload = deepcopy(self.breakdown)
        payload["global_analysis"]["story_contract"] = {"promise": "revised after approval"}
        self.fixture.breakdown_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertTrue(self.validate())

    def test_snapshot_hash_is_time_independent_but_disk_bound(self) -> None:
        a = self.fixture.snapshot_for(created_at="2026-01-01T00:00:00Z")
        b = self.fixture.snapshot_for(created_at="2027-01-01T00:00:00Z")
        self.assertEqual(a["context_hash"], b["context_hash"])
        self.assertFalse(a["inclusion"]["full_screenplay_included"])
        self.assertTrue(a["baseline_files"])

    def test_snapshot_overflow_fails_instead_of_silently_dropping_evidence(self) -> None:
        for limits in ({"max_scenes": 0}, {"max_beats": 0}, {"max_findings": 0}, {"max_context_bytes": 100}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.fixture.snapshot_for(**limits)

    def test_snapshot_preserves_relevant_cross_role_decision(self) -> None:
        decision = {
            "id": "dec-001", "scene_ids": ["scn-001"], "source_refs": ["L1-L4"],
            "topic": "Repair marks", "affected_role_ids": ["director", "art"],
            "conflict": "Subtle realism competes with visual legibility.",
            "options": ["subtle marks", "clear marks"], "recommended_option": "clear marks",
            "decision_owner": "user", "required_by": "concept design",
            "decision": "Keep the repair marks visible on chr-001.", "status": "accepted",
        }
        self.breakdown["cross_role_decisions"] = [decision]
        self.fixture.persist_baseline()
        snapshot = self.fixture.snapshot_for()
        self.assertIn(decision, snapshot["cross_role_decisions"])

    def test_snapshot_includes_findings_linked_only_by_relevant_beat(self) -> None:
        finding = self.breakdown["role_reports"][3]["findings"][0]
        finding.update(scene_ids=[], source_refs=[], beat_ids=["bea-001"],
                       observation="The turn cannot preserve the intended material continuity.",
                       impact="The shot may break continuity.", recommendation="Keep the repaired seam visible.")
        self.fixture.persist_baseline()
        snapshot = self.fixture.snapshot_for()
        self.assertIn(finding, snapshot["role_findings"])
        self.assertIn(finding["id"], snapshot["inclusion"]["finding_ids"])

    def test_finding_blocker_requires_upstream_resolution(self) -> None:
        finding = self.breakdown["role_reports"][3]["findings"][0]
        finding.update(severity="blocker", scene_ids=[], source_refs=[], beat_ids=["bea-001"],
                       observation="The required physical change is infeasible.",
                       impact="The action cannot be produced.", recommendation="Resolve the production method first.")
        self.fixture.persist_baseline()
        snapshot = self.fixture.snapshot_for()
        self.assertEqual(snapshot["ai_feasibility"]["blockers"], [])
        self.assertEqual(snapshot["handoff"]["blocked_by"], [])
        with self.assertRaises(ValueError):
            self.fixture.make()
        finding.update(severity="medium", impact="A verified practical mechanism now supports the action.",
                       recommendation="Use the tested replacement mechanism; retain routine continuity review.")
        self.fixture.persist_baseline()
        snapshot, requirement, position = self.fixture.make()
        self.assertEqual(director.validate_requirement(requirement, snapshot, position), [])

    def test_roundtrip_validates_all_four_asset_types(self) -> None:
        for asset_id in ("chr-001", "loc-001", "scn-001", "prp-001"):
            with self.subTest(asset_id=asset_id):
                snapshot, requirement, position = self.fixture.make(asset_id)
                self.assertEqual(director.validate_requirement(requirement, snapshot, position), [])
                serialized = json.loads(json.dumps(requirement))
                self.assertEqual(director.requirement_hash(serialized), requirement["integrity"]["requirement_hash"])

    def test_requirement_requires_snapshot_and_position(self) -> None:
        self.assertTrue(director.validate_requirement(self.requirement))
        self.assertTrue(director.validate_requirement(self.requirement, self.snapshot))

    def test_user_override_is_a_valid_final_decision(self) -> None:
        requirement = deepcopy(self.requirement)
        requirement["high_impact_decisions"][0].update(status="user_override", chosen_option="用户明确保留更华丽但可生产的袖口", original_recommendation="行为驱动的克制设计")
        requirement = self.fixture.approve(requirement, self.snapshot, self.position)
        self.assertEqual(self.validate(requirement), [])

    def test_semantically_invalid_contracts_cannot_be_sealed(self) -> None:
        cases = {
            "empty_dimension": lambda r: r["design_dimensions"]["shared"].update(dramatic_function=""),
            "wrong_json_type": lambda r: r.update(cultural_boundaries="must be an array"),
            "nonobservable_dimension": lambda r: r["design_dimensions"]["shared"].update(dramatic_function={}),
            "missing_dimension": lambda r: r["design_dimensions"]["type_specific"].pop("growth_stage"),
            "fake_evidence": lambda r: r["evidence"][0].update(source_refs=["L999-L1000"]),
            "malformed_evidence": lambda r: r["evidence"][0].update(source_refs=["some invented source"]),
            "missing_evidence": lambda r: r["evidence"][0].update(source_refs=[]),
            "wrong_type": lambda r: r["asset"].update(asset_type="hero_prop"),
            "renamed_asset": lambda r: r["asset"].update(name="unrelated replacement"),
            "cross_asset_state": lambda r: r["derived_states"][0].update(asset_id="loc-001"),
            "open_question": lambda r: r.update(open_questions=["Which era?"]),
            "unresolved_decision": lambda r: r["high_impact_decisions"][0].update(status="proposed"),
            "prompt_field": lambda r: r.update(generation_prompt="forbidden"),
            "reference_not_user_provided": lambda r: r.update(reference_images=[{"source": "web", "controls": ["palette"], "must_not_control": ["identity"]}]),
        }
        for label, change in cases.items():
            with self.subTest(case=label):
                payload = deepcopy(self.requirement)
                change(payload)
                with self.assertRaises(ValueError):
                    self.fixture.approve(payload, self.snapshot, self.position)

    def test_nested_dimensions_reject_unresolved_or_unobservable_content(self) -> None:
        invalid_values = [
            {"status": "unknown", "reason": "undecided"},
            {"silhouette": "", "material": None},
            {"status": "not_applicable", "reason": "   "},
            {"status": "tbd", "reason": "discuss later"},
            42,
            True,
            ["clear outline", {"shape": ""}],
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                payload = deepcopy(self.requirement)
                payload["design_dimensions"]["type_specific"]["silhouette_negative_space"] = value
                for event in payload["confirmations"]:
                    event["content_hash"] = director.confirmation_hash(payload, event["gate"])
                payload["integrity"]["requirement_hash"] = director.requirement_hash(payload)
                self.assertTrue(director.validate_requirement(payload, self.snapshot, self.position))
                with self.assertRaises(ValueError):
                    director.seal_requirement(payload, self.snapshot, self.position)
        valid = deepcopy(self.requirement)
        valid["design_dimensions"]["shared"]["frame"] = {"framing": "full-body", "use_case": ["reference master"]}
        valid["design_dimensions"]["type_specific"]["bound_props"] = {"status": "not_applicable", "reason": "No prop is permanently part of the character silhouette."}
        valid = self.fixture.approve(valid, self.snapshot, self.position)
        self.assertEqual(self.validate(valid), [])

    def test_original_document_change_invalidates_unchanged_extraction(self) -> None:
        original = self.base / "original-script.docx"
        original.write_bytes(b"synthetic original document version 1")
        provenance = self.breakdown["source_manifest"]["analysis_provenance"]
        provenance["original_source_path"] = str(original)
        provenance["original_source_hash"] = hashlib.sha256(original.read_bytes()).hexdigest()
        self.fixture.persist_baseline()
        snapshot, requirement, position = self.fixture.make()
        self.assertEqual(director.validate_requirement(requirement, snapshot, position), [])
        original.write_bytes(b"synthetic original document version 2")
        self.assertEqual(director.freshness_report(self.breakdown)["status"], "stale")
        self.assertTrue(director.validate_requirement(requirement, snapshot, position))

    def test_removing_derived_state_requires_new_design_confirmation(self) -> None:
        payload = deepcopy(self.requirement)
        payload["derived_states"] = []
        self.assertTrue(self.validate(payload))
        payload = self.fixture.approve(payload, self.snapshot, self.position)
        self.assertEqual(self.validate(payload), [])

    def test_design_change_invalidates_confirmation_even_after_integrity_reseal(self) -> None:
        payload = deepcopy(self.requirement)
        payload["primary_state"]["design_direction"] = "A materially different approved-looking direction"
        payload["integrity"]["requirement_hash"] = director.requirement_hash(payload)
        self.assertTrue(self.validate(payload))
        with self.assertRaises(ValueError):
            director.seal_requirement(payload, self.snapshot, self.position)

    def test_destination_change_invalidates_persistence_confirmation(self) -> None:
        payload = deepcopy(self.requirement)
        payload["persistence_plan"]["output_root"] = str(self.base / "different-output")
        payload["integrity"]["requirement_hash"] = director.requirement_hash(payload)
        self.assertTrue(self.validate(payload))
        with self.assertRaises(ValueError):
            director.materialize(self.catalog, self.snapshot, self.requirement, self.position, self.base / "different-output")

    def test_confirmations_must_be_distinct_user_events_in_order(self) -> None:
        cases = {
            "missing_gate": lambda r: r["confirmations"].pop(),
            "same_message": lambda r: r["confirmations"][1].update(message_ref=r["confirmations"][0]["message_ref"]),
            "assistant_approval": lambda r: r["confirmations"][1].update(confirmed_by="assistant"),
            "reversed_time": lambda r: r["confirmations"][2].update(confirmed_at="2026-08-26T00:00:00Z"),
            "ambiguous_timestamp": lambda r: r["confirmations"][2].update(confirmed_at="yesterday"),
        }
        for label, change in cases.items():
            with self.subTest(case=label):
                payload = deepcopy(self.requirement)
                change(payload)
                payload["integrity"]["requirement_hash"] = director.requirement_hash(payload)
                self.assertTrue(self.validate(payload))

    def test_creative_position_content_is_bound_to_approved_requirement(self) -> None:
        position = deepcopy(self.position)
        position["claim"] = "A completely new creative position"
        self.assertTrue(self.validate(position=position))
        position = deepcopy(self.position)
        position["evidence"] = ["L999"]
        with self.assertRaises(ValueError):
            self.fixture.approve(self.requirement, self.snapshot, position)

    def test_forged_snapshot_or_catalog_is_rejected(self) -> None:
        snapshot = deepcopy(self.snapshot)
        snapshot["global_visual_context"]["story_contract"] = {"tampered": True}
        self.assertTrue(self.validate(snapshot=snapshot))
        catalog = deepcopy(self.catalog)
        catalog["source_hash"] = "b" * 64
        self.assertTrue(director.validate_catalog_snapshot(catalog, self.snapshot))

    def test_scene_requires_sealed_location_dependency_and_pure_environment_scope(self) -> None:
        snapshot, requirement, position = self.fixture.make("scn-001")
        for change in (
            lambda r: r.update(output_scope="character_blocking"),
            lambda r: r.update(dependency_assets=[]),
            lambda r: r["dependency_assets"][0].update(requirement_hash="f" * 64),
        ):
            payload = deepcopy(requirement)
            change(payload)
            with self.assertRaises(ValueError):
                self.fixture.approve(payload, snapshot, position)
        dependency_path = Path(requirement["dependency_assets"][0]["requirement_path"])
        dependency = json.loads(dependency_path.read_text())
        dependency["invariants"] = ["changed after scene approval"]
        dependency_path.write_text(json.dumps(dependency))
        self.assertTrue(director.validate_requirement(requirement, snapshot, position))

    def test_materialize_writes_complete_package_and_does_not_overwrite(self) -> None:
        report = director.materialize(self.catalog, self.snapshot, self.requirement, self.position, self.fixture.output_root)
        self.assertEqual(report["status"], "succeeded")
        version_dir = self.fixture.output_root / "bird-nest" / "draft-1" / "assets" / "chr-001" / "v1"
        self.assertTrue(version_dir.is_dir())
        for filename in ("context-snapshot.json", "creative-position.json", "decision-log.md", "requirement.json", "requirement.md", "asset-catalog.json"):
            self.assertTrue((version_dir / filename).is_file(), filename)
        materialized = json.loads((version_dir / "requirement.json").read_text())
        self.assertEqual(self.validate(materialized), [])
        before = {p.name: p.read_bytes() for p in version_dir.iterdir()}
        retry = director.materialize(self.catalog, self.snapshot, self.requirement, self.position, self.fixture.output_root)
        self.assertEqual(retry["status"], "succeeded")
        self.assertEqual(before, {p.name: p.read_bytes() for p in version_dir.iterdir()})
        changed = deepcopy(self.requirement)
        changed["primary_state"]["design_direction"] = "New direction requiring a new asset version"
        changed = self.fixture.approve(changed, self.snapshot, self.position)
        with self.assertRaises(ValueError):
            director.materialize(self.catalog, self.snapshot, changed, self.position, self.fixture.output_root)

    def test_failed_materialization_has_no_partial_package_and_can_retry(self) -> None:
        original = Path.write_text
        calls = 0
        def fail_second_write(path, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated storage failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", new=fail_second_write):
            with self.assertRaises(OSError):
                director.materialize(self.catalog, self.snapshot, self.requirement, self.position, self.fixture.output_root)
        version_dir = self.fixture.output_root / "bird-nest" / "draft-1" / "assets" / "chr-001" / "v1"
        self.assertFalse(version_dir.exists())
        self.assertEqual(list(version_dir.parent.iterdir()), [])
        result = director.materialize(self.catalog, self.snapshot, self.requirement, self.position, self.fixture.output_root)
        self.assertEqual(result["status"], "succeeded")


    def test_cli_seal_and_materialize_use_same_contract(self) -> None:
        requirement_path = self.fixture.write_package()
        argv = [sys.executable, str(SKILL_ROOT / "scripts" / "concept_director.py")]
        common = ["--requirement", str(requirement_path), "--snapshot", str(requirement_path.parent / "context-snapshot.json"),
                  "--position", str(requirement_path.parent / "creative-position.json")]
        check = subprocess.run([*argv, "validate-requirement", *common], text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertTrue(json.loads(check.stdout)["valid"])
        output = self.base / "sealed.json"
        seal = subprocess.run([*argv, "seal", *common, "--output", str(output)], text=True, capture_output=True)
        self.assertEqual(seal.returncode, 0, seal.stdout + seal.stderr)
        self.assertEqual(json.loads(output.read_text())["confirmations"], self.requirement["confirmations"])
        materialize = subprocess.run([*argv, "materialize", *common,
                                      "--catalog", str(requirement_path.parent / "asset-catalog.json"),
                                      "--output-root", str(self.fixture.output_root)], text=True, capture_output=True)
        self.assertEqual(materialize.returncode, 0, materialize.stdout + materialize.stderr)
        self.assertEqual(json.loads(materialize.stdout)["status"], "succeeded")

    def test_digest_command_does_not_create_user_confirmation(self) -> None:
        payload = deepcopy(self.requirement)
        payload["confirmations"] = []
        path = self.fixture.write_package(payload)
        before = path.read_bytes()
        completed = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "concept_director.py"),
                                    "confirmation-digest", "--requirement", str(path), "--gate", "asset_selection"],
                                   text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["content_hash"], director.confirmation_hash(payload, "asset_selection"))
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            director.seal_requirement(payload, self.snapshot, self.position)


class ContractAndBehaviorTests(unittest.TestCase):
    def test_bundled_analyzer_matches_packaging_lock(self) -> None:
        bundled = REPO / "plugins" / "skill-orchestrator" / "skills" / "ai-script-breakdown"
        lock = json.loads((REPO / "plugins" / "skill-orchestrator" / "locks" / "ai-script-breakdown.lock.json").read_text())
        actual = {str(p.relative_to(bundled)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(bundled.rglob("*"))
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}}
        self.assertEqual(actual, lock["files"])

    def test_gold_examples_cover_four_asset_types(self) -> None:
        payload = json.loads((REPO / "evals" / "concept-grill-gold.json").read_text(encoding="utf-8"))
        counts = {}
        for case in payload["cases"]:
            counts[case["asset_type"]] = counts.get(case["asset_type"], 0) + 1
            self.assertGreaterEqual(len(case["expected_dimensions"]), 2)
        self.assertEqual(counts, {"character_master": 5, "location_master": 5, "scene_state": 5, "hero_prop": 5})


if __name__ == "__main__":
    unittest.main()
