"""Unit tests for scripts/native_bridge.py. No model, no network, no sleeping."""

from __future__ import annotations

import ast
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BRIDGE_PATH = SCRIPTS / "native_bridge.py"

_spec = importlib.util.spec_from_file_location("native_bridge_under_test", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)
rt = bridge.rt

USER_TEXT = "按这个方案开始执行。"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_node(node_id: str, depends_on: list[str] | None = None, idempotent: bool = True,
              mode: str = "parallel", bindings: list[str] | None = None) -> dict:
    return {
        "node_id": node_id, "role_skill": f"role-{node_id}", "objective": f"objective for {node_id}",
        "input_bindings": [{"from": item} for item in (bindings if bindings is not None else ["context.shared_known"])],
        "output_schema": "AgentResultV1", "depends_on": depends_on or [],
        "execution_mode": mode, "idempotent": idempotent,
        "soft_timeout_seconds": 60, "hard_timeout_seconds": 120,
        "permissions": ["filesystem:write_private_node_directory"], "side_effects": ["local_artifacts"],
        "risk": "low", "verification": ["covers the objective"],
    }


def make_graph(nodes: list[dict], max_concurrency: int = 2) -> dict:
    return {"schema_version": "ExecutionGraphV2", "graph_version": 1, "max_concurrency": max_concurrency,
            "max_replans": 0, "nodes": nodes}


def context_item(item_id: str, statement: str) -> dict:
    return {"id": item_id, "statement": statement, "provenance": "test fixture", "status": "confirmed"}


def make_contract(source: Path, with_user_text: bool = True) -> dict:
    confirmations = [{"source": "earlier scope agreement", "scope": "project"}]
    if with_user_text:
        confirmations.append({"source": "user latest message", "text": USER_TEXT, "scope": "this run"})
    return {
        "schema_version": "RequirementContractV2", "goal": "exercise the bridge", "audience": ["tests"],
        "target_platform": "unittest", "in_scope": ["bridge"], "out_of_scope": ["models"],
        "constraints": ["no network"], "acceptance_criteria": ["all states reachable"],
        "authoritative_input": {"semantic_type": "fixture", "path": str(source), "sha256": sha(source.read_bytes())},
        "collaboration_context": {
            "schema_version": "CollaborationContextV1", "version": 1,
            "shared_known": [context_item("C01", "KNOWN-FACT")],
            "user_context_gaps": [context_item("G01", "GAP-FACT")],
            "agent_added_context": [context_item("A01", "AGENT-ADDED-FACT")],
            "joint_unknown_hypotheses": [context_item("H01", "HYPOTHESIS-FACT")],
        },
        "confirmations": confirmations, "open_questions": [],
    }


class BridgeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        self.source = self.tmp / "authoritative.md"
        self.source.write_text("authoritative input v1\n", encoding="utf-8")

    # ----- harness -----
    def call(self, *argv: object, expect: int | None = 0) -> dict:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = bridge.main([str(item) for item in argv])
        payload = json.loads(buffer.getvalue())  # exactly one JSON document on stdout
        if expect is not None:
            self.assertEqual(code, expect, payload)
            self.assertEqual(payload["ok"], code == 0)
        payload["_code"] = code
        return payload

    def cmd(self, name: str, *argv: object, expect: int | None = 0) -> dict:
        return self.call(name, "--run-dir", self.run_dir, *argv, expect=expect)

    def write_inputs(self, nodes: list[dict], max_concurrency: int = 2, contract: dict | None = None) -> None:
        contract = contract or make_contract(self.source)
        (self.run_dir / "requirement.json").write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
        (self.run_dir / "graph.json").write_text(json.dumps(make_graph(nodes, max_concurrency)), encoding="utf-8")

    def start(self, nodes: list[dict], max_concurrency: int = 2, approve: bool = True) -> None:
        self.write_inputs(nodes, max_concurrency)
        self.cmd("init")
        if approve:
            self.cmd("approve", "--from-contract")

    def claim(self, *argv: object) -> dict[str, dict]:
        return {item["node_id"]: item for item in self.cmd("claim", *argv)["claimed"]}

    def write_result(self, task: dict, status: str = "succeeded", artifacts: list[dict] | None = None,
                     questions: list | None = None, task_id: str | None = None, errors: list[str] | None = None) -> None:
        result = {
            "schema_version": "AgentResultV1", "task_id": task_id or task["task_id"], "status": status,
            "claims": [{"id": "K1", "statement": "done"}], "evidence_refs": [], "artifact_refs": artifacts or [],
            "conflicts": [], "questions": questions or [], "errors": errors or [],
        }
        Path(task["result_path"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    def artifact(self, task: dict, name: str = "position.json", body: str = '{"note": "ok"}') -> dict:
        path = Path(task["private_workspace"]) / name
        path.write_text(body, encoding="utf-8")
        return {"path": str(path), "sha256": sha(body.encode("utf-8")), "semantic_type": "position"}

    def finish(self, task: dict, worker: str = "agent-1", **result: object) -> dict:
        self.write_result(task, **result)
        return self.cmd("submit", "--node", task["node_id"], "--worker", worker)

    def node_state(self, node_id: str) -> dict:
        snapshot = bridge.BridgeStore(self.run_dir / "events.sqlite3").snapshot(self.run_id())
        return next(item for item in snapshot["nodes"] if item["node_id"] == node_id)

    def run_id(self) -> str:
        return json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))["run_id"]

    def events(self, kind: str | None = None) -> list[dict]:
        events = bridge.BridgeStore(self.run_dir / "events.sqlite3").events(self.run_id())
        return [item for item in events if kind is None or item["kind"] == kind]

    def make_overdue(self, node_id: str) -> None:
        """Backdate the lease in the projection instead of sleeping."""
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        connection = sqlite3.connect(self.run_dir / "events.sqlite3")
        try:
            with connection:
                changed = connection.execute("UPDATE nodes SET lease_expires_at=? WHERE node_id=?", (past, node_id)).rowcount
        finally:
            connection.close()
        self.assertEqual(changed, 1)


class RuntimeLocationTests(BridgeCase):
    def test_doctor_uses_sibling_runtime_after_relocation(self) -> None:
        copied = self.tmp / "elsewhere" / "plugin" / "skills" / "skill-orchestrator" / "scripts"
        copied.mkdir(parents=True)
        for name in ("native_bridge.py", "orchestrator_runtime.py"):
            shutil.copy2(SCRIPTS / name, copied / name)
        done = subprocess.run([sys.executable, str(copied / "native_bridge.py"), "doctor"],
                              capture_output=True, text=True, cwd=self.tmp, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(Path(payload["runtime_path"]).parent, copied.resolve())
        self.assertEqual(Path(payload["runtime_module"]), (copied / "orchestrator_runtime.py").resolve())
        self.assertEqual(payload["runtime_sha256"], sha((copied / "orchestrator_runtime.py").read_bytes()))
        self.assertEqual(payload["third_party_dependencies"], [])

    def test_in_place_doctor_points_at_this_checkout(self) -> None:
        payload = self.call("doctor")
        self.assertEqual(Path(payload["runtime_path"]), SCRIPTS / "orchestrator_runtime.py")

    def test_source_has_no_versioned_or_absolute_paths(self) -> None:
        source = BRIDGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/0.8", source)
        self.assertIsNone(re.search(r"/\d+\.\d+(\.\d+)?/", source))
        for needle in ("/Users/", "plugins/cache", str(Path.home())):
            self.assertNotIn(needle, source)

    def test_bridge_imports_only_stdlib(self) -> None:
        tree = ast.parse(BRIDGE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in item.names)
            elif isinstance(item, ast.ImportFrom):
                imported.add((item.module or "").split(".")[0])
        self.assertEqual(imported - set(sys.stdlib_module_names), set())


class InitAndApprovalTests(BridgeCase):
    def test_init_rejects_authoritative_hash_mismatch(self) -> None:
        self.write_inputs([make_node("a")])
        self.source.write_text("changed after the contract was written\n", encoding="utf-8")
        payload = self.cmd("init", expect=2)
        self.assertEqual(payload["error"], "validation_failed")
        self.assertIn("hash mismatch", " ".join(payload["errors"]))
        self.assertFalse((self.run_dir / "run.json").exists())
        self.assertFalse((self.run_dir / "events.sqlite3").exists())

    def test_init_rejects_invalid_graph(self) -> None:
        for label, nodes, concurrency in (
            ("cycle", [make_node("a", ["b"]), make_node("b", ["a"])], 2),
            ("missing dependency", [make_node("a", ["ghost"])], 2),
            ("concurrency", [make_node("a")], 7),
        ):
            with self.subTest(label):
                self.write_inputs(nodes, concurrency)
                payload = self.cmd("init", expect=2)
                self.assertEqual(payload["error"], "validation_failed")
                self.assertFalse((self.run_dir / "run.json").exists())

    def test_init_rejects_invalid_requirement_and_bad_workspace(self) -> None:
        contract = make_contract(self.source)
        contract["open_questions"] = ["still unclear"]
        self.write_inputs([make_node("a")], contract=contract)
        self.cmd("init", expect=2)
        outside = make_node("a")
        outside["private_workspace"] = str(self.tmp / "outside")
        self.write_inputs([outside])
        self.assertEqual(self.cmd("init", expect=2)["error"], "private_workspace_outside_run_dir")
        shared = [make_node("a"), make_node("b")]
        shared[0]["private_workspace"] = shared[1]["private_workspace"] = "nodes/same"
        self.write_inputs(shared)
        self.assertEqual(self.cmd("init", expect=2)["error"], "private_workspace_shared")
        self.assertFalse((self.run_dir / "run.json").exists())

    def test_init_succeeds_once(self) -> None:
        self.write_inputs([make_node("a")])
        payload = self.cmd("init")
        self.assertEqual(payload["run_status"], "awaiting_initial_confirmation")
        self.assertEqual(self.run_id(), payload["run_id"])
        self.assertEqual(self.cmd("init", expect=2)["error"], "run_already_initialized")

    def test_commands_before_init_are_refused(self) -> None:
        self.assertEqual(self.cmd("status", expect=4)["error"], "run_not_initialized")
        self.assertEqual(self.call("status", "--run-dir", self.tmp / "missing", expect=2)["error"], "run_dir_not_found")
        self.assertFalse((self.tmp / "missing").exists())

    def test_claim_requires_initial_approval(self) -> None:
        self.start([make_node("a")], approve=False)
        payload = self.cmd("claim", expect=3)
        self.assertEqual(payload["error"], "initial_confirmation_required")
        self.assertEqual(self.cmd("status")["run_status"], "awaiting_initial_confirmation")
        self.assertEqual(self.node_state("a")["status"], "pending")

    def test_approve_from_contract_needs_quoted_user_text(self) -> None:
        self.write_inputs([make_node("a")], contract=make_contract(self.source, with_user_text=False))
        self.cmd("init")
        self.assertEqual(self.cmd("approve", "--from-contract", expect=3)["error"], "no_quoted_confirmation_in_contract")
        self.assertEqual(self.cmd("approve", "--source", "chat", expect=3)["error"], "approval_needs_user_text_and_source")
        self.assertEqual(self.cmd("approve", "--text", "go", expect=3)["error"], "approval_needs_user_text_and_source")
        self.cmd("claim", expect=3)
        self.assertEqual(self.events("approval_recorded"), [])

    def test_approve_from_contract_quotes_user_text(self) -> None:
        self.start([make_node("a")])
        details = self.events("approval_recorded")[0]["payload"]["details"]
        self.assertEqual(details["text"], USER_TEXT)
        self.assertEqual(details["source"], "user latest message")

    def test_requirement_edit_after_init_blocks_claim(self) -> None:
        self.start([make_node("a")])
        contract = make_contract(self.source)
        contract["goal"] = "silently widened goal"
        (self.run_dir / "requirement.json").write_text(json.dumps(contract), encoding="utf-8")
        self.assertEqual(self.cmd("claim", expect=2)["error"], "requirement_changed_since_init")
        self.assertEqual(self.node_state("a")["status"], "pending")


class ClaimTests(BridgeCase):
    def test_claim_respects_max_concurrency(self) -> None:
        self.start([make_node("a"), make_node("b"), make_node("c")], max_concurrency=2)
        first = self.cmd("claim")
        self.assertEqual([item["node_id"] for item in first["claimed"]], ["a", "b"])
        self.assertEqual(first["in_flight"], ["a", "b"])
        second = self.cmd("claim")
        self.assertEqual(second["claimed"], [])
        self.assertEqual(second["ready"], ["c"])
        self.finish(first["claimed"][0])
        self.assertEqual(list(self.claim()), ["c"])

    def test_claim_max_flag_lowers_but_never_raises_the_cap(self) -> None:
        self.start([make_node("a"), make_node("b"), make_node("c")], max_concurrency=2)
        self.assertEqual(list(self.claim("--max", 1)), ["a"])
        self.assertEqual(list(self.claim("--max", 3)), ["b"])
        self.assertEqual(list(self.claim("--max", 3)), [])

    def test_serial_node_runs_alone(self) -> None:
        self.start([make_node("a", mode="serial"), make_node("b")], max_concurrency=3)
        self.assertEqual(list(self.claim()), ["a"])
        self.assertEqual(list(self.claim()), [])

    def test_dependencies_gate_claims_and_results_flow_downstream(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"], bindings=["a.claims"])])
        claimed = self.claim()
        self.assertEqual(list(claimed), ["a"])
        self.finish(claimed["a"])
        task = json.loads(Path(self.claim()["b"]["task_path"]).read_text(encoding="utf-8"))
        self.assertEqual(task["dependency_results"]["a"]["status"], "succeeded")

    def test_task_contains_only_bound_context(self) -> None:
        self.start([make_node("a", bindings=["context.shared_known", "requirement.goal"]),
                    make_node("b", bindings=["context.agent_added_context.A01"])])
        claimed = self.claim()
        text_a = Path(claimed["a"]["task_path"]).read_text(encoding="utf-8")
        task_a = json.loads(text_a)
        self.assertEqual(set(task_a["context_projection"]), {"schema_version", "version", "shared_known"})
        self.assertEqual(task_a["requirement_projection"], {"goal": "exercise the bridge"})
        self.assertIn("KNOWN-FACT", text_a)
        for hidden in ("GAP-FACT", "AGENT-ADDED-FACT", "HYPOTHESIS-FACT", USER_TEXT):
            self.assertNotIn(hidden, text_a)
        text_b = Path(claimed["b"]["task_path"]).read_text(encoding="utf-8")
        self.assertEqual(set(json.loads(text_b)["context_projection"]), {"schema_version", "version", "agent_added_context"})
        self.assertNotIn("KNOWN-FACT", text_b)
        self.assertEqual(task_a["dispatcher_signature"], rt.sign_task(task_a, (self.run_dir / ".bridge" / "dispatcher.key").read_text()))

    def test_concurrent_claims_do_not_double_lease(self) -> None:
        self.start([make_node("a"), make_node("b"), make_node("c")], max_concurrency=2)
        command = [sys.executable, str(BRIDGE_PATH), "claim", "--run-dir", str(self.run_dir)]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
        claimed = []
        for process in processes:
            out, err = process.communicate(timeout=120)
            self.assertEqual(process.returncode, 0, err)
            claimed += [item["node_id"] for item in json.loads(out)["claimed"]]
        self.assertEqual(sorted(claimed), ["a", "b"])
        self.assertEqual(self.cmd("status")["in_flight"], ["a", "b"])
        sequence = [item["seq"] for item in self.events()]
        self.assertEqual(sequence, list(range(1, len(sequence) + 1)))
        leases = [item for item in self.events("node_status_changed") if item["payload"]["status"] == "leased"]
        self.assertEqual(len(leases), 2)


class SubmitTests(BridgeCase):
    def setUp(self) -> None:
        super().setUp()
        self.start([make_node("a"), make_node("b", ["a"])])
        self.task = self.claim()["a"]

    def assert_rejected(self, fragment: str, *argv: object, error: str = "result_rejected") -> dict:
        before = self.node_state("a")
        count = len(self.events())
        payload = self.cmd("submit", "--node", "a", *(argv or ("--worker", "agent-1")), expect=2)
        self.assertEqual(payload["error"], error)
        self.assertIn(fragment, json.dumps(payload, ensure_ascii=False))
        self.assertEqual(self.node_state("a"), before)
        self.assertEqual(len(self.events()), count)
        return payload

    def test_rejects_wrong_task_id(self) -> None:
        self.write_result(self.task, task_id="run-other:a:1")
        self.assert_rejected("task_id does not match dispatch")

    def test_rejects_tampered_task_json(self) -> None:
        path = Path(self.task["task_path"])
        task = json.loads(path.read_text(encoding="utf-8"))
        task["objective"] = "do something broader"
        path.write_text(json.dumps(task), encoding="utf-8")
        self.write_result(self.task)
        self.assert_rejected("task_signature_mismatch", error="task_signature_mismatch")

    def test_rejects_artifact_outside_private_workspace(self) -> None:
        outside = self.run_dir / "leak.txt"
        outside.write_text("leak", encoding="utf-8")
        self.write_result(self.task, artifacts=[{"path": str(outside), "sha256": sha(b"leak")}])
        self.assert_rejected("escaped private workspace")
        sneaky = Path(self.task["private_workspace"]) / ".." / ".." / "leak.txt"
        self.write_result(self.task, artifacts=[{"path": str(sneaky), "sha256": sha(b"leak")}])
        self.assert_rejected("escaped private workspace")

    def test_rejects_artifact_hash_mismatch_and_missing_fields(self) -> None:
        ref = self.artifact(self.task)
        self.write_result(self.task, artifacts=[{**ref, "sha256": "0" * 64}])
        self.assert_rejected("hash mismatch")
        self.write_result(self.task, artifacts=[{"path": ref["path"]}])
        self.assert_rejected("needs path and sha256")
        self.write_result(self.task, artifacts=[{"path": str(Path(self.task["private_workspace"]) / "absent.json"), "sha256": "0" * 64}])
        self.assert_rejected("artifact missing")

    def test_rejects_malformed_result(self) -> None:
        Path(self.task["result_path"]).write_text('{"schema_version": "AgentResultV1"}', encoding="utf-8")
        self.assert_rejected("invalid AgentResultV1 status")
        Path(self.task["result_path"]).write_text("[]", encoding="utf-8")
        self.assert_rejected("JSON object")

    def test_requires_worker_identity(self) -> None:
        self.write_result(self.task)
        before = self.node_state("a")
        payload = self.cmd("submit", "--node", "a", expect=2)
        self.assertIn("worker identity required", " ".join(payload["errors"]))
        self.assertEqual(self.node_state("a"), before)

    def test_worker_may_come_from_result_but_must_not_contradict(self) -> None:
        self.write_result(self.task)
        path = Path(self.task["result_path"])
        result = json.loads(path.read_text(encoding="utf-8")) | {"native_agent_id": "agent-7"}
        path.write_text(json.dumps(result), encoding="utf-8")
        self.assert_rejected("contradicts", "--worker", "agent-1")
        payload = self.cmd("submit", "--node", "a")
        self.assertEqual(payload["worker"], "agent-7")
        self.assertEqual(self.node_state("a")["thread_id"], "agent-7")

    def test_missing_result_and_wrong_state(self) -> None:
        self.assertEqual(self.cmd("submit", "--node", "a", "--worker", "x", expect=4)["error"], "result_missing")
        self.assertEqual(self.cmd("submit", "--node", "b", "--worker", "x", expect=4)["error"], "node_not_in_flight")
        self.assertEqual(self.cmd("submit", "--node", "zzz", "--worker", "x", expect=2)["error"], "unknown_node")

    def test_accepts_valid_result_with_relative_artifact(self) -> None:
        ref = self.artifact(self.task)
        payload = self.finish(self.task, artifacts=[{**ref, "path": "position.json"}])
        self.assertEqual(payload["node_status"], "succeeded")
        self.assertEqual(payload["artifacts_recorded"], 1)
        self.assertEqual(payload["next"], "claim")
        recorded = self.events("artifact_recorded")[0]["payload"]
        self.assertEqual(recorded, {"node_id": "a", "path": ref["path"], "sha256": ref["sha256"], "kind": "position"})
        self.assertEqual(self.cmd("submit", "--node", "a", "--worker", "agent-1", expect=4)["error"], "node_not_in_flight")

    def test_late_result_rejected_unless_accepted(self) -> None:
        self.write_result(self.task)
        self.make_overdue("a")
        self.assertEqual(self.cmd("status")["overdue"], ["a"])
        payload = self.cmd("submit", "--node", "a", "--worker", "agent-1", expect=4)
        self.assertEqual(payload["error"], "lease_expired")
        self.assertEqual(self.node_state("a")["status"], "running")
        self.assertEqual(self.events("late_result_accepted"), [])
        accepted = self.cmd("submit", "--node", "a", "--worker", "agent-1", "--accept-late")
        self.assertTrue(accepted["late"])
        self.assertEqual(accepted["node_status"], "succeeded")
        late = self.events("late_result_accepted")
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0]["payload"]["node_id"], "a")
        self.assertEqual(late[0]["payload"]["attempt"], 1)


class RetryAndExpiryTests(BridgeCase):
    def test_idempotent_node_retries_once_then_fails_and_skips_downstream(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"]), make_node("c", ["b"])])
        first = self.claim()["a"]
        payload = self.finish(first, status="failed", errors=["boom"])
        self.assertEqual(payload["node_status"], "retry_scheduled")
        self.assertEqual(payload["nodes"]["b"], "pending")
        second = self.claim()["a"]
        self.assertEqual(second["attempt"], 2)
        self.assertNotEqual(second["task_id"], first["task_id"])
        self.assertFalse(Path(second["result_path"]).exists())  # stale result moved aside
        payload = self.finish(second, status="failed", errors=["boom again"])
        self.assertEqual(payload["node_status"], "failed")
        self.assertEqual(payload["nodes"], {"a": "failed", "b": "skipped", "c": "skipped"})
        self.assertTrue(payload["complete"])
        self.assertEqual(self.claim(), {})
        final = self.cmd("finalize")
        self.assertEqual(final["run_status"], "failed")
        self.assertIsNone(final["next"])
        self.assertEqual(self.cmd("accept", "--text", "ok", "--source", "chat", expect=4)["error"], "run_not_acceptable")

    def test_stale_attempt_result_is_rejected_on_retry(self) -> None:
        self.start([make_node("a")])
        first = self.claim()["a"]
        self.finish(first, status="failed")
        second = self.claim()["a"]
        self.write_result(second, task_id=first["task_id"])
        payload = self.cmd("submit", "--node", "a", "--worker", "agent-1", expect=2)
        self.assertIn("task_id does not match dispatch", payload["errors"])

    def test_non_idempotent_node_fails_without_retry(self) -> None:
        self.start([make_node("a", idempotent=False), make_node("b", ["a"])])
        payload = self.finish(self.claim()["a"], status="failed")
        self.assertEqual(payload["nodes"], {"a": "failed", "b": "skipped"})

    def test_expire_retries_idempotent_node_once_then_fails(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"])])
        self.claim()
        self.assertEqual(self.cmd("expire")["expired"], {})  # nothing overdue yet
        self.assertEqual(self.cmd("expire", "--node", "a", expect=4)["error"], "lease_still_valid")
        self.make_overdue("a")
        self.assertEqual(self.cmd("finalize", expect=4)["overdue"], ["a"])
        payload = self.cmd("expire")
        self.assertEqual(payload["expired"], {"a": "retry_scheduled"})
        self.assertIn("hard timeout", self.node_state("a")["last_error"])
        self.assertEqual(self.claim()["a"]["attempt"], 2)
        self.make_overdue("a")
        payload = self.cmd("expire")
        self.assertEqual(payload["expired"], {"a": "failed"})
        self.assertEqual(payload["nodes"], {"a": "failed", "b": "skipped"})
        self.assertEqual(payload["next"], "finalize")
        self.assertEqual(self.cmd("expire", "--node", "a", expect=4)["error"], "node_not_in_flight")
        self.assertEqual(len([item for item in self.events("metric_recorded") if item["payload"]["name"] == "hard_timeout"]), 2)

    def test_expire_fails_non_idempotent_node_and_force_works(self) -> None:
        self.start([make_node("a", idempotent=False)])
        self.claim()
        self.assertEqual(self.cmd("expire", "--node", "a", "--force")["expired"], {"a": "failed"})


class DegradedTests(BridgeCase):
    def test_single_agent_mode_is_serial_root_only_and_degraded(self) -> None:
        self.start([make_node("a"), make_node("b")], max_concurrency=2)
        first = self.cmd("claim", "--single-agent", "--reason", "host has no collaboration agents")
        self.assertEqual([item["node_id"] for item in first["claimed"]], ["a"])
        self.assertTrue(first["degraded_mode"])
        task = first["claimed"][0]
        self.assertEqual(json.loads(Path(task["task_path"]).read_text())["execution"], "single_agent_serial_degraded")
        self.write_result(task)
        rejected = self.cmd("submit", "--node", "a", "--worker", "agent-1", expect=2)
        self.assertIn("worker must be root", " ".join(rejected["errors"]))
        self.assertEqual(self.node_state("a")["status"], "running")
        self.cmd("submit", "--node", "a", "--worker", "root")
        second = self.claim()  # degraded mode is sticky even without the flag
        self.assertEqual(list(second), ["b"])
        self.finish(second["b"], worker="root")
        final = self.cmd("finalize")
        self.assertEqual(final["run_status"], "degraded_pending_acceptance")
        self.assertTrue(final["degraded"])
        self.assertIn("single_agent_serial_execution", final["degraded_reasons"])

    def test_multi_node_graph_done_by_root_is_auto_degraded(self) -> None:
        self.start([make_node("a"), make_node("b")])
        for task in self.claim().values():
            self.finish(task, worker="/root")
        final = self.cmd("finalize")
        self.assertEqual(final["run_status"], "degraded_pending_acceptance")
        self.assertEqual(final["degraded_reasons"], ["no_independent_native_worker"])
        report = json.loads((self.run_dir / "run_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["native_agents"], [])

    def test_degraded_result_status_degrades_run(self) -> None:
        self.start([make_node("a")])
        self.finish(self.claim()["a"], status="degraded")
        final = self.cmd("finalize")
        self.assertEqual(final["run_status"], "degraded_pending_acceptance")
        self.assertEqual(final["degraded_reasons"], ["node_result_degraded"])

    def test_degraded_flag_survives_accept(self) -> None:
        self.start([make_node("a"), make_node("b")])
        for task in self.claim().values():
            self.finish(task, worker="root")
        self.cmd("finalize")
        accepted = self.cmd("accept", "--text", "降级结果我接受", "--source", "user chat")
        self.assertEqual(accepted["run_status"], "approved")
        self.assertTrue(accepted["degraded"])
        self.assertEqual(accepted["degraded_reasons"], ["no_independent_native_worker"])
        report = json.loads((self.run_dir / "run_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["final_status"], "approved")
        self.assertTrue(report["degraded"])
        self.assertEqual(report["degraded_reasons"], ["no_independent_native_worker"])
        snapshot = json.loads((self.run_dir / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["degraded"], 1)
        final = [item for item in snapshot["approvals"] if item["gate"] == "final"]
        self.assertTrue(json.loads(final[0]["details_json"])["accepted_degraded"])
        self.assertEqual(self.cmd("accept", "--text", "again", "--source", "chat", expect=4)["error"], "run_not_acceptable")
        self.assertEqual(self.cmd("cancel", "--reason", "too late", expect=4)["error"], "run_already_terminal")


class BlockedTests(BridgeCase):
    def test_blocked_result_waits_for_user_and_resumes_same_attempt(self) -> None:
        self.start([make_node("a"), make_node("b")], max_concurrency=2)
        claimed = self.claim()
        questions = [{"id": f"Q{index}", "question": f"question {index}?"} for index in range(1, 6)]
        payload = self.finish(claimed["a"], status="blocked", questions=questions)
        self.assertEqual(payload["node_status"], "awaiting_input")
        self.assertEqual(payload["run_status"], "awaiting_user")
        self.assertEqual(payload["next"], "answer")
        self.assertEqual([item["id"] for item in payload["pending_questions"]], ["Q1", "Q2", "Q3"])
        self.assertEqual(payload["pending_questions"][0]["node_id"], "a")
        self.assertEqual(self.cmd("claim", expect=4)["error"], "run_not_claimable")
        self.assertEqual(self.cmd("finalize", expect=4)["error"], "run_not_finalizable")
        # a second node blocking while the run already waits never grows the list past three
        other = self.finish(claimed["b"], status="blocked", questions=["plain text question"])
        self.assertEqual(len(other["pending_questions"]), 3)
        answers = self.tmp / "answers.json"
        answers.write_text(json.dumps({"Q1": "yes", "Q2": "no", "Q3": "later"}), encoding="utf-8")
        answered = self.cmd("answer", "--file", answers, "--source", "user chat")
        self.assertEqual(answered["run_status"], "running")
        self.assertEqual(answered["pending_questions"], [])
        self.assertEqual(answered["ready"], ["a", "b"])
        again = self.claim()
        self.assertEqual(again["a"]["attempt"], 1)
        self.assertEqual(again["a"]["task_id"], claimed["a"]["task_id"])
        task = json.loads(Path(again["a"]["task_path"]).read_text(encoding="utf-8"))
        self.assertEqual(task["user_input"], {"answers": {"Q1": "yes", "Q2": "no", "Q3": "later"}, "source": "user chat"})
        self.assertFalse(Path(again["a"]["result_path"]).exists())
        self.assertEqual(self.finish(again["a"])["node_status"], "succeeded")
        self.assertEqual(self.node_state("a")["attempts"], 1)
        self.finish(again["b"], worker="agent-2")
        self.assertEqual(self.cmd("finalize")["run_status"], "proposed")

    def test_other_in_flight_results_are_still_accepted_while_waiting(self) -> None:
        self.start([make_node("a"), make_node("b")], max_concurrency=2)
        claimed = self.claim()
        self.finish(claimed["a"], status="blocked", questions=[{"id": "Q1", "question": "which?"}])
        payload = self.finish(claimed["b"], worker="agent-2")
        self.assertEqual(payload["node_status"], "succeeded")
        self.assertEqual(payload["run_status"], "awaiting_user")
        self.assertEqual(len(payload["pending_questions"]), 1)

    def test_answer_refused_when_not_waiting(self) -> None:
        self.start([make_node("a")])
        answers = self.tmp / "answers.json"
        answers.write_text("{}", encoding="utf-8")
        self.assertEqual(self.cmd("answer", "--file", answers, "--source", "chat", expect=4)["error"], "run_not_awaiting_user")
        self.assertEqual(self.events("user_input_recorded"), [])


class FinalizeAndCancelTests(BridgeCase):
    def test_finalize_refuses_incomplete_run(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"])])
        self.assertEqual(self.cmd("finalize", expect=4)["error"], "run_not_finalizable")  # not even started
        task = self.claim()["a"]
        payload = self.cmd("finalize", expect=4)
        self.assertEqual(payload["error"], "run_incomplete")
        self.assertEqual(payload["in_flight"], ["a"])
        self.finish(task)
        self.assertEqual(self.cmd("finalize", expect=4)["ready"], ["b"])
        self.assertFalse((self.run_dir / "run_report.json").exists())
        self.assertEqual(self.cmd("status")["run_status"], "running")

    def test_finalize_writes_verified_report(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"])])
        task_a = self.claim()["a"]
        self.finish(task_a, worker="agent-1", artifacts=[self.artifact(task_a)])
        task_b = self.claim()["b"]
        self.finish(task_b, worker="agent-2", artifacts=[self.artifact(task_b, "notes.txt", "notes")])
        final = self.cmd("finalize")
        self.assertEqual(final["run_status"], "proposed")
        self.assertFalse(final["degraded"])
        report = json.loads((self.run_dir / "run_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], "RunReportV2")
        self.assertEqual(report["run_id"], self.run_id())
        self.assertEqual(report["final_status"], "proposed")
        self.assertEqual(report["native_agents"], ["agent-1", "agent-2"])
        self.assertEqual(len(report["artifacts"]), 2)
        self.assertEqual(report["validation"], {
            "requirement_valid": True, "requirement_unchanged_since_init": True, "graph_valid": True,
            "artifact_hashes_valid": True, "private_node_outputs_valid": True,
        })
        self.assertEqual([(node["node_id"], node["status"], node["worker"]) for node in report["nodes"]],
                         [("a", "succeeded", "agent-1"), ("b", "succeeded", "agent-2")])
        self.assertEqual(Path(report["executor"]["runtime_path"]), SCRIPTS / "orchestrator_runtime.py")
        audit = json.loads((self.run_dir / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["schema_version"], "RunAuditExportV1")
        self.assertTrue((self.run_dir / "snapshot.json").is_file())
        self.assertNotIn("dispatcher.key", json.dumps(audit))
        # an artifact modified after submission is caught when the report is rebuilt
        Path(report["artifacts"][0]["path"]).write_text("tampered", encoding="utf-8")
        self.assertFalse(self.cmd("finalize")["validation"]["artifact_hashes_valid"])
        accepted = self.cmd("accept", "--text", "可以，采纳。", "--source", "user chat")
        self.assertEqual(accepted["run_status"], "approved")
        self.assertFalse(accepted["degraded"])

    def test_cancel_mid_run(self) -> None:
        self.start([make_node("a"), make_node("b", ["a"]), make_node("c")], max_concurrency=1)
        task = self.claim()["a"]
        self.finish(task)
        self.claim()
        payload = self.cmd("cancel", "--reason", "user changed direction")
        self.assertEqual(payload["run_status"], "canceled")
        self.assertEqual(payload["nodes"], {"a": "succeeded", "b": "canceled", "c": "canceled"})
        self.assertEqual(payload["in_flight"], [])
        self.assertEqual(self.events("cancel_reason_recorded")[0]["payload"]["reason"], "user changed direction")
        report = json.loads((self.run_dir / "run_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["final_status"], "canceled")
        self.assertEqual(json.loads((self.run_dir / "snapshot.json").read_text(encoding="utf-8"))["status"], "canceled")
        self.assertEqual(self.cmd("claim", expect=4)["error"], "run_not_claimable")
        self.write_result(task)
        self.assertEqual(self.cmd("submit", "--node", "b", "--worker", "x", expect=4)["error"], "run_not_accepting_results")
        self.assertEqual(self.cmd("cancel", "--reason", "again", expect=4)["error"], "run_already_terminal")
        self.assertEqual(self.cmd("finalize")["run_status"], "canceled")

    def test_cancel_before_approval_and_while_awaiting_user(self) -> None:
        self.start([make_node("a")], approve=False)
        self.assertEqual(self.cmd("cancel", "--reason", "never mind")["nodes"], {"a": "canceled"})
        self.assertEqual(self.cmd("approve", "--from-contract", expect=4)["error"], "run_not_awaiting_initial_confirmation")

        self.run_dir = self.tmp / "run2"
        self.run_dir.mkdir()
        self.start([make_node("a")])
        self.finish(self.claim()["a"], status="blocked", questions=[{"id": "Q1", "question": "?"}])
        payload = self.cmd("cancel", "--reason", "user withdrew")
        self.assertEqual(payload["run_status"], "canceled")
        self.assertEqual(payload["nodes"], {"a": "canceled"})


if __name__ == "__main__":
    unittest.main()
