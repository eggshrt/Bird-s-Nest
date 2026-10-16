"""Lossless dispatch projection checks; no paid agents or image generation."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from concept_fixtures import ConceptFixture

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/skill-orchestrator/skills/image-prompt-team/scripts/image_prompt_team.py"
SPEC = importlib.util.spec_from_file_location("image_prompt_projection_test", SCRIPT)
team = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(team)


class CaptureClient:
    def __init__(self):
        self.tasks = []

    def run_agent(self, task, *args, **kwargs):
        self.tasks.append(deepcopy(task))
        return team.base_result(task["task_id"]), "test-thread"

    def archive_thread(self, thread_id):
        pass


class SnapshotStore:
    def __init__(self, nodes):
        self.nodes = nodes

    def snapshot(self, run_id):
        return {"nodes": self.nodes}


def dispatch_measurements(requirement, requirement_path, project):
    """Measure the actual CodexExecutor task JSON, with a capturing test client.

    Results are only serialized characters/UTF-8 bytes. They exclude skill loading,
    model responses and runtime overhead and do not estimate tokens or output quality.
    """
    requirement_hash = team.file_hash(requirement_path)
    presentation = team.recommend_presentation(requirement)
    context = team.build_context(requirement)
    graph = team.build_graph(requirement)
    nodes = graph["nodes"] + [op["node"] for op in team.build_compile_patch(graph)["operations"]]
    client = CaptureClient()
    executor = team.CodexExecutor(client, requirement, requirement_hash, presentation, context,
                                  "test-dispatcher-key", "projection-test", project, SnapshotStore(nodes))
    deterministic = team.DeterministicExecutor(requirement, requirement_hash, presentation, "projection-test")
    results, rows = {}, []
    for node in nodes:
        dependencies = {key: results[key] for key in node["depends_on"]}
        executor(node, dependencies, 1)
        projected = client.tasks[-1]
        legacy = deepcopy(projected)
        legacy.update({"requirement": requirement, "collaboration_context_projection": context,
                       "dependency_results": dependencies,
                       "constraints": ["single_asset", "no_user_interview", "no_files", "no_image_generation", "no_design_redesign"]})
        legacy["dispatcher_signature"] = team.sign_task(legacy, "test-dispatcher-key")
        # AppServerClient.run_agent uses precisely this JSON serialization.
        before, after = [json.dumps(value, ensure_ascii=False, indent=2) for value in (legacy, projected)]
        rows.append({"node": node["node_id"], "chars_before": len(before), "chars_after": len(after),
                     "bytes_before": len(before.encode("utf-8")), "bytes_after": len(after.encode("utf-8"))})
        results[node["node_id"]] = deterministic(node, dependencies, 1)[0]
    totals = {key: sum(row[key] for row in rows) for key in ("chars_before", "chars_after", "bytes_before", "bytes_after")}
    return {"measurement": "indent-2 dispatch JSON only; not tokens, model quality or runtime",
            "node_count": len(nodes), "totals": totals, "nodes": rows}


class PromptProjectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.fixture = ConceptFixture(self.base)
        self.path = self.fixture.write_package()
        self.requirement = team.load_validated_requirement(self.path)
        self.requirement_hash = team.file_hash(self.path)
        self.context = team.build_context(self.requirement)
        self.node = next(node for node in team.build_graph(self.requirement)["nodes"] if node["node_id"] == "position-color_light")

    def project(self, requirement=None, node=None, context=None, dependencies=None):
        return team.build_task_projection(node or self.node, requirement or self.requirement,
                                          dependencies or {}, self.context if context is None else context,
                                          self.requirement_hash)

    def assert_retained(self, requirement, projected):
        if projected["schema_version"] == "VisualAssetRequirementV1":
            self.assertEqual(projected, requirement)
            return
        self.assertEqual(projected["schema_version"], "RoleRequirementViewV1")
        for key, value in requirement.items():
            if key != "schema_version" and key not in team.RUNTIME_REQUIREMENT_FIELDS:
                self.assertEqual(projected[key], value, key)
        self.assertTrue(set(team.RUNTIME_REQUIREMENT_FIELDS).isdisjoint(projected))

    def test_all_four_sealed_asset_types_preserve_every_design_and_constraint(self):
        for asset_id in ("chr-001", "loc-001", "scn-001", "prp-001"):
            with self.subTest(asset_id=asset_id):
                snapshot, requirement, position = self.fixture.make(asset_id)
                path = self.fixture.write_package(requirement, snapshot, position, self.base / asset_id / "requirement.json")
                validated = team.load_validated_requirement(path)
                graph = team.build_graph(validated)
                nodes = graph["nodes"] + [op["node"] for op in team.build_compile_patch(graph)["operations"]]
                for node in nodes:
                    projected = team.build_task_projection(node, validated, {}, team.build_context(validated), team.file_hash(path))
                    self.assert_retained(validated, projected["requirement"])
                    if node["role_skill"] in team.FULL_REQUIREMENT_ROLES:
                        self.assertEqual(projected["requirement"], validated)
                    else:
                        self.assertEqual(projected["requirement"]["source_requirement_hash"], team.file_hash(path))
                if asset_id == "scn-001":
                    self.assertEqual(validated["output_scope"], "pure_environment")
                    self.assertEqual(validated["dependency_assets"][0]["ref_asset_id"], "loc-001")

    def test_user_override_references_and_derived_state_survive(self):
        requirement = deepcopy(self.requirement)
        requirement["high_impact_decisions"][0].update({"status": "user_override", "original_recommendation": "减少服装层级"})
        reference = self.base / "reference.png"
        reference.write_bytes(b"synthetic-reference-content")
        requirement["reference_images"] = [{"source": "user_provided", "path": str(reference),
                                             "sha256": team.file_hash(reference), "controls": ["material"],
                                             "must_not_control": ["identity", "composition"]}]
        requirement = self.fixture.approve(requirement, self.fixture.snapshot, self.fixture.position)
        path = self.fixture.write_package(requirement)
        validated = team.load_validated_requirement(path)
        reference_node = next(node for node in team.build_graph(validated)["nodes"] if node["node_id"] == "reference-role")
        view = self.project(requirement=validated, node=reference_node, context=team.build_context(validated))["requirement"]
        self.assert_retained(validated, view)
        self.assertEqual(view["high_impact_decisions"][0]["status"], "user_override")
        self.assertTrue(view["derived_states"])
        self.assertEqual(view["reference_images"], validated["reference_images"])

    def test_exact_duplicate_context_is_replaced_by_inline_evidence_pointer(self):
        projected = self.project()
        context = projected["collaboration_context_projection"]
        self.assertEqual(context["shared_known"], [])
        self.assertEqual(context["schema_version"], "CollaborationContextViewV1")
        self.assertEqual(context["source_context_schema"], "CollaborationContextV1")
        self.assertEqual(context["shared_known_ref"]["from"], "requirement.evidence")
        self.assertEqual(context["shared_known_ref"]["source_requirement_hash"], self.requirement_hash)
        self.assertEqual(projected["requirement"]["evidence"], self.requirement["evidence"])
        for key in ("user_context_gaps", "agent_added_context", "joint_unknown_hypotheses"):
            self.assertEqual(context[key], self.context[key])

    def test_independent_context_and_changes_to_existing_evidence_are_not_dropped(self):
        context = deepcopy(self.context)
        context["shared_known"][0]["status"] = "disputed"
        context["shared_known"].append({"statement": "A new cross-role concern"})
        self.assertEqual(self.project(context=context)["collaboration_context_projection"], context)

    def test_dependency_substance_and_nonempty_summary_metrics_are_retained(self):
        result = team.base_result("original-task", "blocked")
        result.update({"summary": "Cannot show the required invariant", "metrics": {"duration_ms": 10},
                       "claims": [{"claim_type": "review", "value": {"recommendation": "wider framing"}}],
                       "evidence_refs": ["L1-L4"], "artifact_refs": [{"path": "inspection.json"}],
                       "conflicts": [{"invariant": "sleeve", "severity": "blocking"}],
                       "questions": [{"question": "Resolve framing"}], "errors": ["missing invariant"]})
        compact = self.project(dependencies={"review": result})["dependency_results"]["review"]
        self.assertNotIn("task_id", compact)
        expected = {key: value for key, value in result.items() if key != "task_id"}
        expected.update({"schema_version": "AgentResultViewV1", "source_result_schema": "AgentResultV1"})
        self.assertEqual(compact, expected)

    def test_unknown_contracts_fall_back_to_complete_payload(self):
        cases = [(dict(self.node, role_skill="future-role"), self.requirement),
                 (self.node, dict(self.requirement, future_constraints={"important": "new"}))]
        for field in team.RUNTIME_REQUIREMENT_FIELDS:
            updated = deepcopy(self.requirement)
            record = updated[field][0] if field == "confirmations" else updated[field]
            record["future_constraint"] = "must preserve"
            cases.append((self.node, updated))
        for node, requirement in cases:
            projected = self.project(node=node, requirement=requirement)
            self.assertEqual(projected["requirement"], requirement)
            self.assertEqual(projected["collaboration_context_projection"], self.context)
        result = team.base_result("task")
        result["future_findings"] = ["must preserve"]
        self.assertEqual(self.project(dependencies={"future": result})["dependency_results"]["future"], result)

    def test_projection_cannot_mutate_sealed_input_or_other_task_views(self):
        before = deepcopy((self.requirement, self.context))
        projected = self.project()
        projected["requirement"]["invariants"].append("mutated")
        projected["collaboration_context_projection"]["agent_added_context"].clear()
        self.assertEqual((self.requirement, self.context), before)
        self.assertNotIn("mutated", self.project()["requirement"]["invariants"])
        self.assertEqual(team.load_validated_requirement(self.path), self.requirement)

    def test_real_dispatch_signs_projected_task_and_explains_view(self):
        client = CaptureClient()
        executor = team.CodexExecutor(client, self.requirement, self.requirement_hash,
                                      team.recommend_presentation(self.requirement), self.context,
                                      "test-key", "test-run", self.base, SnapshotStore([self.node]))
        executor(self.node, {}, 1)
        task = client.tasks[0]
        self.assertEqual(task["requirement"]["schema_version"], "RoleRequirementViewV1")
        self.assertEqual(task["dispatcher_signature"], team.sign_task(task, "test-key"))
        self.assertIn(team.ROLE_VIEW_INSTRUCTION, task["constraints"])
        self.assertEqual(self.requirement["schema_version"], "VisualAssetRequirementV1")

    def test_actual_dispatch_serialization_is_smaller_without_skipping_roles(self):
        measured = dispatch_measurements(self.requirement, self.path, self.base)
        self.assertEqual(measured["node_count"], 14)
        self.assertLess(measured["totals"]["bytes_after"], measured["totals"]["bytes_before"])
        self.assertLess(measured["totals"]["chars_after"], measured["totals"]["chars_before"])


if __name__ == "__main__":
    unittest.main()
