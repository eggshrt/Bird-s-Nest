from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins" / "skill-orchestrator" / "skills" / "skill-orchestrator" / "scripts" / "orchestrator_runtime.py"
SPEC = importlib.util.spec_from_file_location("orchestrator_runtime_test", SCRIPT)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(runtime)


def context() -> dict:
    return {
        "schema_version": "CollaborationContextV1",
        "shared_known": [{"id": "K1", "statement": "one sealed asset", "provenance": "contract", "confidence": 1.0, "impact": "high", "status": "confirmed", "verification": "hash"}],
        "user_context_gaps": [], "agent_added_context": [], "joint_unknown_hypotheses": [],
    }


def contract() -> dict:
    return {
        "schema_version": "RequirementContractV2", "goal": "produce one prompt",
        "asset_input": {"asset_id": "chr-001", "asset_type": "character_master", "requirement_path": "/tmp/requirement.json", "requirement_hash": "a" * 64},
        "audience": ["beginner"], "target_platform": "openai", "in_scope": ["one prompt"],
        "out_of_scope": ["images"], "constraints": ["single asset"], "acceptance_criteria": [],
        "collaboration_context": context(), "confirmations": [], "open_questions": [],
    }


def node(node_id: str, depends_on: list[str] | None = None, idempotent: bool = True, mode: str = "parallel") -> dict:
    return {
        "node_id": node_id, "role_skill": f"role-{node_id}", "objective": f"objective {node_id}",
        "input_bindings": [{"name": "source", "from": "requirement.asset_input"}],
        "output_schema": "AgentResultV1", "depends_on": depends_on or [], "execution_mode": mode,
        "idempotent": idempotent, "soft_timeout_seconds": 2, "hard_timeout_seconds": 4,
        "permissions": ["project:read"], "side_effects": [], "risk": "low",
        "verification": {"method": "schema"},
    }


def graph(nodes: list[dict]) -> dict:
    return {"schema_version": "ExecutionGraphV2", "graph_version": 1, "max_concurrency": 3, "max_replans": 1, "nodes": nodes}


def result(task_id: str, status: str = "succeeded", errors: list[str] | None = None) -> dict:
    return {
        "schema_version": "AgentResultV1", "task_id": task_id, "status": status,
        "summary": status, "claims": [], "evidence_refs": [], "artifact_refs": [],
        "conflicts": [], "questions": [], "errors": errors or [], "metrics": {},
    }


class RuntimeV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def store(self) -> object:
        return runtime.EventStore(self.base / "runtime-v2.sqlite3")

    def create_confirmed(self, graph_value: dict) -> tuple[object, str]:
        store = self.store()
        run_id = store.create_run(contract(), graph_value)
        store.record_approval(run_id, "initial", "confirmed")
        return store, run_id

    def test_legacy_database_is_preserved_and_refused(self) -> None:
        path = self.base / "runtime-v2.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE legacy_runs(id TEXT)")
            connection.execute("INSERT INTO legacy_runs VALUES ('keep-me')")
        with self.assertRaises(runtime.LegacySchemaError):
            runtime.EventStore(path)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("SELECT id FROM legacy_runs").fetchone()[0], "keep-me")

    def test_event_replay_rebuilds_projections(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))
        store.set_node_status(run_id, "A", "leased", attempts=1)
        store.set_node_status(run_id, "A", "running", attempts=1)
        store.set_node_status(run_id, "A", "succeeded", attempts=1)
        before = store.snapshot(run_id)
        store.replay(run_id)
        after = store.snapshot(run_id)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["nodes"][0]["status"], after["nodes"][0]["status"])

    def test_duplicate_event_id_is_rejected_atomically(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))
        event_id = "fixed-event"
        store.append(run_id, "metric_recorded", {"name": "one", "value": 1}, event_id=event_id)
        with self.assertRaises(sqlite3.IntegrityError):
            store.append(run_id, "metric_recorded", {"name": "two", "value": 2}, event_id=event_id)
        self.assertEqual([item["name"] for item in store.snapshot(run_id)["metrics"]], ["one"])

    def test_scheduler_respects_topology_and_parallel_cap(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A"), node("B"), node("C", ["A", "B"], mode="serial")]))
        active = 0
        peak = 0
        lock = threading.Lock()
        calls: list[str] = []

        def executor(definition: dict, dependencies: dict, attempt: int) -> tuple[dict, None]:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            calls.append(definition["node_id"])
            with lock:
                active -= 1
            return result(f"{run_id}:{definition['node_id']}:{attempt}"), None

        snapshot = runtime.Scheduler(store, concurrency=3, heartbeat_seconds=1).execute(run_id, executor)
        self.assertEqual(snapshot["status"], "proposed")
        self.assertLessEqual(peak, 3)
        self.assertGreaterEqual(peak, 2)
        self.assertEqual(calls[-1], "C")

    def test_idempotent_failure_retries_once(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))

        def executor(definition: dict, dependencies: dict, attempt: int) -> tuple[dict, None]:
            status = "failed" if attempt == 1 else "succeeded"
            return result(f"{run_id}:A:{attempt}", status, ["transient"] if status == "failed" else []), None

        snapshot = runtime.Scheduler(store, heartbeat_seconds=1).execute(run_id, executor)
        self.assertEqual(snapshot["status"], "proposed")
        self.assertEqual(snapshot["nodes"][0]["attempts"], 2)
        self.assertEqual(sum(item["name"] == "retry" for item in snapshot["metrics"]), 1)

    def test_non_idempotent_failure_is_not_retried(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A", idempotent=False)]))
        snapshot = runtime.Scheduler(store).execute(
            run_id,
            lambda definition, dependencies, attempt: (result(f"{run_id}:A:{attempt}", "failed", ["write state unknown"]), None),
        )
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["nodes"][0]["attempts"], 1)

    def test_expired_lease_is_recovered(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))
        store.set_node_status(run_id, "A", "leased", attempts=1, lease_owner="dead", lease_expires_at="2000-01-01T00:00:00+00:00")
        store.set_node_status(run_id, "A", "running", attempts=1, lease_owner="dead", lease_expires_at="2000-01-01T00:00:00+00:00")
        self.assertEqual(store.recover_expired_leases(run_id), ["A"])
        self.assertEqual(store.snapshot(run_id)["nodes"][0]["status"], "retry_scheduled")

    def test_invalid_state_transition_is_rejected(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))
        with self.assertRaisesRegex(ValueError, "Invalid node transition"):
            store.set_node_status(run_id, "A", "succeeded", attempts=1)
        with self.assertRaisesRegex(ValueError, "Invalid run transition"):
            store.set_run_status(run_id, "approved")

    def test_blocking_questions_are_deduplicated_and_capped_at_three(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A"), node("B")]))

        def executor(definition: dict, dependencies: dict, attempt: int) -> tuple[dict, None]:
            value = result(f"{run_id}:{definition['node_id']}:{attempt}", "blocked")
            value["questions"] = [
                {"id": "same", "question": "共同问题"},
                {"id": definition["node_id"], "question": f"问题 {definition['node_id']}"},
            ]
            return value, None

        snapshot = runtime.Scheduler(store).execute(run_id, executor)
        self.assertEqual(snapshot["status"], "awaiting_user")
        self.assertLessEqual(len(snapshot["pending_questions"]), 3)
        self.assertEqual(sum(item["id"] == "same" for item in snapshot["pending_questions"]), 1)

    def test_external_cancel_interrupts_active_executor(self) -> None:
        store, run_id = self.create_confirmed(graph([node("A")]))

        class CancelableExecutor:
            def __init__(self) -> None:
                self.released = threading.Event()
                self.canceled_nodes: list[str] = []

            def __call__(self, definition: dict, dependencies: dict, attempt: int) -> tuple[dict, None]:
                self.released.wait(5)
                return result(f"{run_id}:A:{attempt}"), None

            def cancel(self, node_id: str) -> None:
                self.canceled_nodes.append(node_id)
                self.released.set()

        executor = CancelableExecutor()
        canceler = threading.Thread(target=lambda: (time.sleep(0.1), store.cancel(run_id)), daemon=True)
        canceler.start()
        snapshot = runtime.Scheduler(store, heartbeat_seconds=1).execute(run_id, executor)
        canceler.join(timeout=2)
        self.assertEqual(snapshot["status"], "canceled")
        self.assertEqual(executor.canceled_nodes, ["A"])

    def test_incremental_patch_invalidates_descendants_and_limits_replan(self) -> None:
        original = graph([node("A"), node("B", ["A"])])
        store, run_id = self.create_confirmed(original)
        patch = {
            "schema_version": "DagPatchV1", "base_graph_version": 1, "semantic_impact": "low",
            "confirmation_required": False, "operations": [{"op": "replace_node", "node": {**node("A"), "objective": "revised objective A"}}],
            "invalidated_nodes": ["A", "B"], "evidence": ["input changed"],
        }
        self.assertEqual(store.register_patch(run_id, patch, automatic=True), {"A", "B"})
        with self.assertRaisesRegex(ValueError, "replan limit"):
            store.register_patch(run_id, {**patch, "base_graph_version": 2}, automatic=True)

    def test_app_server_skill_invocation_includes_skill_input_item(self) -> None:
        class FakeClient(runtime.AppServerClient):
            def __init__(self) -> None:
                super().__init__(["unused"])
                self.calls: list[tuple[str, dict]] = []

            def request(self, method: str, params: dict | None = None, timeout: float = 30) -> object:
                params = params or {}
                self.calls.append((method, params))
                if method == "thread/start":
                    return {"thread": {"id": "thread-1"}}
                if method == "turn/start":
                    task_id = "run:A:1"
                    payload = json.dumps(result(task_id))
                    with self._condition:
                        self._completed["thread-1"] = {"turn": {"status": "completed", "items": [{"type": "agentMessage", "text": payload}]}}
                    return {"turn": {"id": "turn-1"}}
                if method == "thread/archive":
                    return {}
                raise AssertionError(method)

        skill_path = self.base / "SKILL.md"
        skill_path.write_text("---\nname: role-a\ndescription: Test role.\n---\n", encoding="utf-8")
        client = FakeClient()
        value, thread_id = client.run_agent(
            {"task_id": "run:A:1"}, "role-a", self.base, {"type": "object"}, 2,
            skill_path=skill_path,
        )
        self.assertEqual(thread_id, "thread-1")
        self.assertEqual(value["status"], "succeeded")
        turn = next(params for method, params in client.calls if method == "turn/start")
        self.assertIn({"type": "skill", "name": "role-a", "path": str(skill_path.resolve())}, turn["input"])
        self.assertEqual(turn["sandboxPolicy"]["type"], "readOnly")


if __name__ == "__main__":
    unittest.main()
