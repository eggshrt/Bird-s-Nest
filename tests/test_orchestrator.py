from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

import yaml


REPO = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO / "plugins" / "skill-orchestrator" / "skills" / "skill-orchestrator"
SCRIPT = SKILL_ROOT / "scripts" / "orchestrator_index.py"
BOOTSTRAP = SKILL_ROOT / "scripts" / "bootstrap_runtime.py"
SPEC = importlib.util.spec_from_file_location("orchestrator_index", SCRIPT)
orchestrator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(orchestrator)


def write_skill(root: Path, directory: str, name: str, description: str, body: str = "# Workflow\nDo the work.") -> Path:
    target = root / directory
    target.mkdir(parents=True, exist_ok=True)
    skill = target / "SKILL.md"
    skill.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8")
    return skill


def roots(*paths: Path) -> list[dict[str, str]]:
    return [{"path": str(path), "scope": f"scope-{index}", "source": f"source-{index}"} for index, path in enumerate(paths)]


class IndexTests(unittest.TestCase):
    def test_precedence_and_shadowed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            high, low = base / "high", base / "low"
            first = write_skill(high, "alpha", "same-skill", "high priority capability")
            second = write_skill(low, "alpha", "same-skill", "low priority capability")
            output = base / "catalog.json"
            catalog = orchestrator.build_catalog(base, output, roots=roots(high, low))
            self.assertEqual(catalog["skills"][0]["path"], str(first.resolve()))
            self.assertEqual(catalog["shadowed"][0]["path"], str(second.resolve()))
            self.assertEqual(catalog["shadowed"][0]["shadowed_by"], str(first.resolve()))

    def test_yaml_error_is_recorded_without_aborting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "skills"
            write_skill(root, "valid", "valid-skill", "valid parsing capability")
            broken = root / "broken"
            broken.mkdir(parents=True)
            (broken / "SKILL.md").write_text("---\nname: [broken\ndescription: bad\n---\n", encoding="utf-8")
            catalog = orchestrator.build_catalog(base, base / "catalog.json", roots=roots(root))
            self.assertEqual(catalog["stats"]["active"], 1)
            self.assertEqual(catalog["stats"]["invalid"], 1)
            self.assertIn("yaml_error", catalog["invalid"][0]["errors"][0])

    def test_content_hash_reuses_then_refreshes_changed_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "skills"
            skill = write_skill(root, "one", "hash-skill", "hash invalidation test")
            output = base / "catalog.json"
            first = orchestrator.build_catalog(base, output, roots=roots(root))
            second = orchestrator.build_catalog(base, output, roots=roots(root))
            self.assertEqual(first["stats"]["refreshed"], 1)
            self.assertEqual(second["stats"]["reused"], 1)
            skill.write_text(skill.read_text() + "\nChanged.\n", encoding="utf-8")
            third = orchestrator.build_catalog(base, output, roots=roots(root))
            self.assertEqual(third["stats"]["refreshed"], 1)
            self.assertNotEqual(first["skills"][0]["content_hash"], third["skills"][0]["content_hash"])

    def test_manual_override_is_applied_after_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "skills"
            write_skill(root, "one", "override-skill", "read a safe report")
            override = base / "overrides.yaml"
            override.write_text("skills:\n  override-skill:\n    risk_level: high\n    confidence: 0.99\n    permissions: [external:write]\n", encoding="utf-8")
            catalog = orchestrator.build_catalog(base, base / "catalog.json", override, roots=roots(root))
            record = catalog["skills"][0]
            self.assertTrue(record["manual_override"])
            self.assertEqual(record["risk_level"], "high")
            self.assertEqual(record["confidence"], 0.99)

    def test_new_user_skill_is_visible_on_immediate_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            user_root = base / ".agents" / "skills"
            output = base / "catalog.json"
            first = orchestrator.build_catalog(base, output, roots=roots(user_root))
            self.assertEqual(first["stats"]["active"], 0)
            write_skill(user_root, "installed", "installed-skill", "newly installed capability")
            second = orchestrator.build_catalog(base, output, roots=roots(user_root))
            self.assertEqual([record["name"] for record in second["skills"]], ["installed-skill"])


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_bm25_retrieves_and_risk_filter_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "skills"
            write_skill(root, "pdf", "pdf-reader", "read render inspect verify PDF documents")
            write_skill(root, "mailer", "email-publisher", "publish and send external email messages")
            output = base / "catalog.json"
            catalog = orchestrator.build_catalog(base, output, roots=roots(root))
            for record in catalog["skills"]:
                if record["name"] == "email-publisher":
                    record["risk_level"] = "high"
            output.write_text(json.dumps(catalog), encoding="utf-8")
            result = await orchestrator.search_catalog(output, "render and verify PDF", limit=3, max_risk="medium")
            self.assertEqual(result["candidates"][0]["name"], "pdf-reader")
            filtered = await orchestrator.search_catalog(output, "publish send external email", limit=3, max_risk="medium")
            self.assertEqual(filtered["candidates"], [])
            self.assertEqual(filtered["filtered"][0]["filter_reasons"], ["risk>medium"])

    async def test_non_ascii_only_query_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "catalog.json"
            catalog.write_text('{"skills": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "English/ASCII"):
                await orchestrator.search_catalog(catalog, "生成图片")


class PlanValidationTests(unittest.TestCase):
    def node(self, node_id: str, depends: list[str] | None = None, binding: str = "requirement.inputs.source") -> dict:
        return {
            "id": node_id,
            "skill": {"name": "sample", "path": "/sample/SKILL.md", "content_hash": "abc"},
            "goal": "produce output",
            "input_bindings": [{"input": "source", "from": binding}],
            "expected_outputs": [{"name": "result", "type": "text"}],
            "depends_on": depends or [],
            "execution_mode": "serial",
            "risk": "low",
            "verification": {"method": "compare", "evidence": "test"},
        }

    def plan(self, nodes: list[dict], max_replans: int = 1, parallel_authorized: bool = False) -> dict:
        return {"schema_version": "ExecutionPlanV1", "parallel_authorized": parallel_authorized, "retry_policy": {"max_replans": max_replans}, "nodes": nodes}

    def test_valid_binding(self) -> None:
        first = self.node("N1")
        second = self.node("N2", ["N1"], "N1.outputs.result")
        self.assertEqual(orchestrator.validate_plan(self.plan([first, second])), [])

    def test_cycle_is_rejected(self) -> None:
        first = self.node("N1", ["N2"], "N2.outputs.result")
        second = self.node("N2", ["N1"], "N1.outputs.result")
        self.assertTrue(any("cycle" in error for error in orchestrator.validate_plan(self.plan([first, second]))))

    def test_unknown_output_binding_is_rejected(self) -> None:
        first = self.node("N1")
        second = self.node("N2", ["N1"], "N1.outputs.missing")
        self.assertTrue(any("unknown output" in error for error in orchestrator.validate_plan(self.plan([first, second]))))

    def test_more_than_one_replan_is_rejected(self) -> None:
        errors = orchestrator.validate_plan(self.plan([self.node("N1")], max_replans=2))
        self.assertTrue(any("max_replans" in error for error in errors))

    def test_parallel_requires_explicit_authorization(self) -> None:
        node = self.node("N1")
        node["execution_mode"] = "parallel"
        errors = orchestrator.validate_plan(self.plan([node], parallel_authorized=False))
        self.assertTrue(any("explicit authorization" in error for error in errors))

    def test_requirement_rejects_open_questions_and_non_english_query(self) -> None:
        contract = {
            "schema_version": "RequirementContractV1",
            "goal": "result",
            "audience": ["user"],
            "inputs": [],
            "deliverables": [],
            "in_scope": [],
            "out_of_scope": [],
            "constraints": [],
            "assumptions": [],
            "acceptance_criteria": [{"id": "AC-1", "criterion": "exists", "method": "inspect"}],
            "open_questions": ["which format"],
            "retrieval_query": "生成文档",
            "retrieval_terms": [],
        }
        errors = orchestrator.validate_requirement(contract)
        self.assertTrue(any("open_questions" in error for error in errors))
        self.assertTrue(any("English/ASCII" in error for error in errors))

    def test_report_enforces_single_replan_and_two_attempt_limit(self) -> None:
        report = {
            "schema_version": "RunReportV1",
            "plan_ref": "plan.json",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:01:00Z",
            "nodes": [{"id": "N1", "status": "failed", "artifacts": [], "validation_evidence": [], "errors": ["failure"], "attempts": 3}],
            "replans_used": 2,
            "final_status": "failed",
            "conclusion": "failed",
        }
        errors = orchestrator.validate_report(report)
        self.assertTrue(any("replans_used" in error for error in errors))
        self.assertTrue(any("attempts" in error for error in errors))


class SecurityAndBehaviorTests(unittest.TestCase):
    def test_external_skill_audit_flags_hidden_executable_network_script(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "candidate", "candidate", "candidate skill")
            candidate = root / "candidate"
            hidden = candidate / ".payload"
            hidden.write_text("secret", encoding="utf-8")
            script = candidate / "scripts" / "run.sh"
            script.parent.mkdir()
            script.write_text("#!/bin/sh\ncurl https://example.com\n", encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
            report = orchestrator.audit_skill(candidate)
            codes = {finding["code"] for finding in report["findings"]}
            self.assertTrue({"hidden_path", "executable_file", "network_call"}.issubset(codes))
            self.assertFalse(report["safe_to_execute"])

    def test_grill_me_is_byte_identical_to_canonical_version(self) -> None:
        path = REPO / "plugins" / "skill-orchestrator" / "skills" / "grill-me" / "SKILL.md"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(digest, "4e14035b7c23d8f4fb92c1bad4e53eb92c9539cbc9184851d007263c060d1eb7")

    def test_orchestrator_is_explicit_only(self) -> None:
        config = yaml.safe_load((SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))
        self.assertFalse(config["policy"]["allow_implicit_invocation"])

    def test_control_protocol_contains_required_behavior_gates(self) -> None:
        body = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "obtain explicit confirmation",
            "Obtain a second explicit confirmation",
            "only when the user explicitly authorizes subagents",
            "Never auto-install",
            "retry at most once",
            "Then rebuild the local index and regenerate the DAG",
        ]
        combined = body + (SKILL_ROOT / "references" / "github-fallback.md").read_text(encoding="utf-8")
        for phrase in required_phrases:
            self.assertIn(phrase, combined)

    def test_bootstrap_dry_run_does_not_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run([sys.executable, str(BOOTSTRAP), "--cache-root", temporary], text=True, capture_output=True)
            payload = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(payload["status"], "confirmation_required")
            self.assertFalse(any(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
