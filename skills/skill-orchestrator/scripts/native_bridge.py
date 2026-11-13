#!/usr/bin/env python3
"""Official file bridge between the V2 event store and host-native collaboration workers.

The scheduler state lives in ``<run-dir>/events.sqlite3``. Every subcommand is a
short, non-blocking step that prints exactly one JSON object, so no process has
to stay alive while a native agent (or the controller itself) does the work.

Run directory contract (nothing else needs to be copied into it):
    requirement.json   RequirementContractV2          (input, frozen at init)
    graph.json         ExecutionGraphV2               (input)
    nodes/<node_id>/   task.json (bridge) / result.json + artifacts (worker)
    run.json, snapshot.json, audit.json, run_report.json   (bridge output)

Concurrency: every subcommand that touches a run directory holds an exclusive
lock on ``<run-dir>/.bridge/lock`` for its whole duration. SQLite transactions
alone are not enough: the runtime computes the event ``seq`` with a read that
precedes its write transaction, and every bridge step is check-then-act.

Exit codes: 0 ok, 2 invalid input, 3 permission/confirmation missing,
4 not ready (wrong state, lease expired, lock busy), 1 internal error.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_PATH = SCRIPT_DIR / "orchestrator_runtime.py"


def _load_runtime() -> Any:
    """Always load the sibling runtime, never whatever happens to be on sys.path."""
    loaded = sys.modules.get("orchestrator_runtime")
    if loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() == RUNTIME_PATH:
        return loaded
    spec = importlib.util.spec_from_file_location("orchestrator_runtime", RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sibling runtime: {RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("orchestrator_runtime", module)
    spec.loader.exec_module(module)
    return module


rt = _load_runtime()

BRIDGE_SCHEMA = "NativeBridgeV1"
LEASE_OWNER = "native-bridge"
ROOT_WORKERS = {"root", "/root"}
DEGRADED_METRIC = "single_agent_serial_degraded"
FINALIZED_EVENT = "bridge_finalized"
CLAIMABLE = {"pending", "ready", "retry_scheduled", "awaiting_input"}
IN_FLIGHT = {"leased", "running"}
DEAD = {"failed", "skipped", "canceled"}
MAX_QUESTIONS = 3
LOCK_TIMEOUT_SECONDS = 30.0
EXIT_INTERNAL, EXIT_INVALID, EXIT_PERMISSION, EXIT_NOT_READY = 1, 2, 3, 4


class BridgeError(Exception):
    def __init__(self, code: int, error: str, **details: Any) -> None:
        super().__init__(error)
        self.code, self.payload = code, {"ok": False, "error": error, **details}


# ---------- small helpers ----------

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def run_lock(run_dir: Path) -> Iterator[None]:
    """Exclusive advisory lock per run directory (flock on POSIX, msvcrt on Windows)."""
    lock_path = run_dir / ".bridge" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    with lock_path.open("a+b") as handle:
        try:
            import fcntl
            acquire = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # noqa: E731
            release = lambda: fcntl.flock(handle, fcntl.LOCK_UN)  # noqa: E731
        except ImportError:  # pragma: no cover - Windows
            import msvcrt
            acquire = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1))  # noqa: E731
            release = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))  # noqa: E731
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise BridgeError(EXIT_NOT_READY, "run_dir_locked", lock=str(lock_path),
                                      hint="another bridge command is still running; retry") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            release()


def plugin_info() -> dict[str, Any]:
    parents = SCRIPT_DIR.parents
    plugin_root = parents[2] if len(parents) > 2 else SCRIPT_DIR
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    version = None
    if manifest.is_file():
        try:
            version = read_json(manifest).get("version")
        except (ValueError, AttributeError):
            version = None
    return {
        "bridge_schema": BRIDGE_SCHEMA, "plugin_version": version,
        "plugin_root": str(plugin_root), "runtime_path": str(RUNTIME_PATH),
        "runtime_sha256": sha256_file(RUNTIME_PATH), "runtime_module": str(Path(rt.__file__).resolve()),
    }


class _ClosingConnection:
    """Commit/rollback like sqlite3's own context manager, then actually close."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self.connection.__enter__()

    def __exit__(self, *exc_info: Any) -> None:
        try:
            self.connection.__exit__(*exc_info)
        finally:
            self.connection.close()


class BridgeStore(rt.EventStore):
    """Runtime store whose connections are closed after each use (the runtime leaks them)."""

    def _connect(self) -> Any:
        return _ClosingConnection(super()._connect())


class Run:
    """Everything a subcommand needs about one run directory."""

    def __init__(self, run_dir: Path, must_exist: bool = True) -> None:
        self.dir = run_dir.resolve()
        self.run_id: str | None = None
        self._store: Any = None
        self._contract: dict[str, Any] | None = None
        marker = self.dir / "run.json"
        if marker.is_file():
            self.run_id = read_json(marker)["run_id"]
        elif must_exist:
            raise BridgeError(EXIT_NOT_READY, "run_not_initialized", hint="run `init` first")

    @property
    def store(self) -> Any:
        if self._store is None:  # lazy: a rejected init must not leave a database behind
            self._store = BridgeStore(self.dir / "events.sqlite3")
        return self._store

    # --- inputs ---
    @property
    def contract(self) -> dict[str, Any]:
        if self._contract is None:
            self._contract = read_json(self.dir / "requirement.json")
        return self._contract

    def frozen_contract(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """requirement.json must still be the contract that was hashed at init."""
        contract = self.contract
        if not isinstance(contract, dict) or rt.hash_json(contract) != snapshot["contract_hash"]:
            raise BridgeError(EXIT_INVALID, "requirement_changed_since_init",
                              hint="contract changes must freeze this run and derive a new run")
        return contract

    @property
    def graph(self) -> dict[str, Any]:
        return self.store.graph(self.run_id)

    def snapshot(self) -> dict[str, Any]:
        return self.store.snapshot(self.run_id)

    def node_states(self) -> dict[str, dict[str, Any]]:
        return {item["node_id"]: item for item in self.snapshot()["nodes"]}

    def workspace(self, node: dict[str, Any]) -> Path:
        declared = node.get("private_workspace")
        path = Path(declared) if declared else self.dir / "nodes" / node["node_id"]
        if not path.is_absolute():
            path = self.dir / path
        path = path.resolve()
        root = self.dir / "nodes"
        if path == root or not path.is_relative_to(root):
            raise BridgeError(EXIT_INVALID, "private_workspace_outside_run_dir", node_id=node["node_id"], path=str(path))
        return path

    def key(self) -> str:
        path = self.dir / ".bridge" / "dispatcher.key"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(secrets.token_hex(32))
        return path.read_text(encoding="utf-8").strip()

    def event(self, kind: str, payload: dict[str, Any], actor: str = "bridge") -> None:
        self.store.append(self.run_id, kind, payload, actor=actor, graph_version=self.store.graph_version(self.run_id))

    def degraded_mode(self, snapshot: dict[str, Any] | None = None) -> bool:
        snapshot = snapshot or self.snapshot()
        return any(item["name"] == DEGRADED_METRIC for item in snapshot["metrics"])


def verify_authoritative_input(contract: dict[str, Any], base: Path) -> list[str]:
    source = contract.get("authoritative_input")
    path_key, hash_key = "path", "sha256"
    if source is None:
        source, path_key, hash_key = contract.get("asset_input") or {}, "requirement_path", "requirement_hash"
    path = Path(str(source.get(path_key, "")))
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        return [f"authoritative input not found: {path}"]
    if sha256_file(path) != source.get(hash_key):
        return [f"authoritative input hash mismatch: {path}"]
    return []


def project_inputs(node: dict[str, Any], contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Task-bounded projection: only the requirement/context parts the node bound."""
    context = contract["collaboration_context"]
    context_part = {key: context[key] for key in ("schema_version", "version") if key in context}
    requirement_part: dict[str, Any] = {}
    for binding in node.get("input_bindings", []):
        scope, _, field = str(binding.get("from", "")).partition(".")
        field = field.split(".", 1)[0]  # `context.shared_known.C01` projects the whole top-level field
        if scope == "context" and field in context:
            context_part[field] = context[field]
        elif scope == "requirement" and field in contract and field != "collaboration_context":
            requirement_part[field] = contract[field]
    return requirement_part, context_part


def propagate_skips(run: Run) -> list[str]:
    graph, skipped = run.graph, []
    changed = True
    while changed:
        changed = False
        states = run.node_states()
        for node in graph["nodes"]:
            node_id = node["node_id"]
            if states[node_id]["status"] in {"pending", "ready"} and any(
                states[dep]["status"] in DEAD for dep in node.get("depends_on", [])
            ):
                run.store.set_node_status(run.run_id, node_id, "skipped", error="failed dependency")
                skipped.append(node_id)
                changed = True
    return skipped


def lease_overdue(state: dict[str, Any]) -> bool:
    expiry = state.get("lease_expires_at")
    return bool(expiry) and datetime.fromisoformat(expiry) < now()


def overview(run: Run) -> dict[str, Any]:
    graph, snapshot = run.graph, run.snapshot()
    states = {item["node_id"]: item for item in snapshot["nodes"]}
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    ready = [
        node_id for node_id in rt.topological_order(graph)
        if states[node_id]["status"] in CLAIMABLE
        and all(states[dep]["status"] == "succeeded" for dep in nodes[node_id].get("depends_on", []))
    ]
    in_flight = [node_id for node_id, state in states.items() if state["status"] in IN_FLIGHT]
    return {
        "run_id": run.run_id, "run_status": snapshot["status"],
        "degraded_mode": run.degraded_mode(snapshot),
        "nodes": {node_id: state["status"] for node_id, state in states.items()},
        "ready": ready, "in_flight": in_flight,
        "overdue": [node_id for node_id in in_flight if lease_overdue(states[node_id])],
        "pending_questions": snapshot["pending_questions"],
        "complete": not ready and not in_flight
        and all(state["status"] in DEAD | {"succeeded"} for state in states.values()),
    }


def require_initial_approval(snapshot: dict[str, Any]) -> None:
    if not any(item["gate"] == "initial" and item["decision"] == "confirmed" for item in snapshot["approvals"]):
        raise BridgeError(EXIT_PERMISSION, "initial_confirmation_required", hint="run `approve` with the user's own words")


# ---------- subcommands ----------

def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": True, **plugin_info(), "python": sys.executable,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "third_party_dependencies": [],
        "note": "bridge + runtime are stdlib-only; bootstrap_runtime.py is only needed by orchestrator_index.py",
    }


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir, must_exist=False)
    if run.run_id:
        raise BridgeError(EXIT_INVALID, "run_already_initialized", run_id=run.run_id)
    contract, graph = run.contract, read_json(run.dir / "graph.json")
    if not isinstance(contract, dict) or not isinstance(graph, dict):
        raise BridgeError(EXIT_INVALID, "validation_failed", errors=["requirement.json and graph.json must be JSON objects"])
    errors = rt.validate_requirement(contract) + rt.validate_graph(graph)
    if not errors:
        errors += verify_authoritative_input(contract, run.dir)
    if errors:
        raise BridgeError(EXIT_INVALID, "validation_failed", errors=errors)
    legacy_context = run.dir / "context.json"
    if legacy_context.is_file() and read_json(legacy_context) != contract["collaboration_context"]:
        raise BridgeError(EXIT_INVALID, "context_json_diverges_from_requirement")
    workspaces: dict[Path, str] = {}
    for node in graph["nodes"]:
        workspace = run.workspace(node)  # rejects workspaces outside <run-dir>/nodes
        if workspace in workspaces:
            raise BridgeError(EXIT_INVALID, "private_workspace_shared",
                              node_ids=[workspaces[workspace], node["node_id"]], path=str(workspace))
        workspaces[workspace] = node["node_id"]
    info = plugin_info()
    run.run_id = run.store.create_run(contract, graph, {
        "executor": "native_file_bridge", "bridge_schema": BRIDGE_SCHEMA,
        "plugin_version": info["plugin_version"], "runtime_sha256": info["runtime_sha256"],
        "scope": args.scope or "", "role_skills": sorted({str(node["role_skill"]) for node in graph["nodes"]}),
    })
    write_json(run.dir / "run.json", {"schema_version": BRIDGE_SCHEMA, "run_id": run.run_id, **info})
    return {"ok": True, "run_id": run.run_id, "run_status": "awaiting_initial_confirmation",
            "requirement_valid": True, "graph_valid": True, "authoritative_input_hash_valid": True, "next": "approve"}


def cmd_approve(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] != "awaiting_initial_confirmation":
        raise BridgeError(EXIT_NOT_READY, "run_not_awaiting_initial_confirmation", run_status=snapshot["status"])
    text, source = args.text, args.source
    if args.from_contract:
        confirmations = [item for item in run.frozen_contract(snapshot).get("confirmations", [])
                         if isinstance(item, dict) and str(item.get("text") or "").strip()]
        if not confirmations:
            raise BridgeError(EXIT_PERMISSION, "no_quoted_confirmation_in_contract")
        text, source = confirmations[-1]["text"], source or confirmations[-1].get("source")
    if not str(text or "").strip() or not str(source or "").strip():
        raise BridgeError(EXIT_PERMISSION, "approval_needs_user_text_and_source")
    run.store.record_approval(run.run_id, "initial", "confirmed", {"text": text, "source": source, "scope": args.scope or ""})
    return {"ok": True, "run_id": run.run_id, "gate": "initial", "decision": "confirmed", "next": "claim"}


def cmd_claim(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    require_initial_approval(snapshot)
    contract = run.frozen_contract(snapshot)
    if snapshot["status"] not in {"awaiting_initial_confirmation", "running"}:
        raise BridgeError(EXIT_NOT_READY, "run_not_claimable", run_status=snapshot["status"])
    if snapshot["status"] == "awaiting_initial_confirmation":
        run.store.set_run_status(run.run_id, "running")
    if args.single_agent and not run.degraded_mode():
        run.event("metric_recorded", {"name": DEGRADED_METRIC, "value": 1, "reason": args.reason or "no native collaboration agents"})
    degraded = run.degraded_mode()
    propagate_skips(run)
    graph, state = run.graph, overview(run)
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    states = run.node_states()
    cap = 1 if degraded else max(1, min(3, int(graph.get("max_concurrency", 3)), args.max or 3))
    slots = cap - len(state["in_flight"])
    if any(nodes[node_id].get("execution_mode") == "serial" for node_id in state["in_flight"]):
        slots = 0
    answers = [event["payload"] for event in run.store.events(run.run_id) if event["kind"] == "user_input_recorded"]
    claimed: list[dict[str, Any]] = []
    for node_id in state["ready"]:
        if slots <= 0:
            break
        node, current = nodes[node_id], states[node_id]
        serial = node.get("execution_mode") == "serial"
        if serial and (state["in_flight"] or claimed):
            continue
        resumed = current["status"] == "awaiting_input"  # same attempt continues after the user's answer
        attempt = max(1, current["attempts"] if resumed else current["attempts"] + 1)
        expiry = (now() + timedelta(seconds=node["hard_timeout_seconds"])).isoformat()
        workspace = run.workspace(node)
        workspace.mkdir(parents=True, exist_ok=True)
        stale = workspace / "result.json"
        if stale.exists():
            index = len(list(workspace.glob("result.superseded.*.json"))) + 1
            stale.replace(workspace / f"result.superseded.{index}.json")
        requirement_part, context_part = project_inputs(node, contract)
        task = {
            "schema_version": "AgentTaskV1", "run_id": run.run_id, "task_id": f"{run.run_id}:{node_id}:{attempt}",
            "node_id": node_id, "attempt": attempt, "role_skill": node["role_skill"], "objective": node["objective"],
            "requirement_projection": requirement_part, "context_projection": context_part,
            "authoritative_input": contract.get("authoritative_input") or contract.get("asset_input"),
            "dependency_results": {dep: states[dep]["result"] for dep in node.get("depends_on", [])},
            "user_input": answers[-1] if answers and resumed else None,
            "constraints": contract["constraints"], "permissions": node["permissions"],
            "verification": node["verification"], "expected_output": "AgentResultV1 at result_path; artifacts only inside private_workspace",
            "soft_timeout_seconds": node["soft_timeout_seconds"], "deadline_at": expiry,
            "private_workspace": str(workspace), "result_path": str(workspace / "result.json"),
            "execution": "single_agent_serial_degraded" if degraded else "native_collaboration_agent",
        }
        task["dispatcher_signature"] = rt.sign_task(task, run.key())
        write_json(workspace / "task.json", task)
        for status in ("leased", "running"):
            run.store.set_node_status(run.run_id, node_id, status, attempts=attempt, lease_owner=LEASE_OWNER, lease_expires_at=expiry)
        claimed.append({key: task[key] for key in ("node_id", "attempt", "task_id", "role_skill", "deadline_at", "private_workspace", "result_path")}
                       | {"task_path": str(workspace / "task.json")})
        slots -= 1
        if serial:
            break
    after = overview(run)
    return {"ok": True, "claimed": claimed, "max_in_flight": cap, **after,
            "next": "dispatch_then_submit" if claimed or after["in_flight"] else ("finalize" if after["complete"] else "blocked")}


def normalize_questions(node_id: str, raw: list[Any]) -> list[dict[str, Any]]:
    questions = []
    for item in raw:
        if isinstance(item, dict):
            questions.append({"node_id": node_id, **item})
        elif isinstance(item, str) and item.strip():
            questions.append({"node_id": node_id, "question": item})
    return questions


def cmd_submit(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] not in {"running", "awaiting_user"}:
        raise BridgeError(EXIT_NOT_READY, "run_not_accepting_results", run_status=snapshot["status"])
    nodes = {node["node_id"]: node for node in run.graph["nodes"]}
    if args.node not in nodes:
        raise BridgeError(EXIT_INVALID, "unknown_node", node_id=args.node)
    node, state = nodes[args.node], run.node_states()[args.node]
    if state["status"] not in IN_FLIGHT:
        raise BridgeError(EXIT_NOT_READY, "node_not_in_flight", node_id=args.node, node_status=state["status"])
    workspace = run.workspace(node)
    task = read_json(workspace / "task.json")
    if not isinstance(task, dict) or not hmac.compare_digest(rt.sign_task(task, run.key()), str(task.get("dispatcher_signature"))):
        raise BridgeError(EXIT_INVALID, "task_signature_mismatch", node_id=args.node)
    attempt = state["attempts"]
    if (task.get("run_id"), task.get("node_id"), task.get("attempt")) != (run.run_id, args.node, attempt):
        raise BridgeError(EXIT_INVALID, "task_not_current_attempt", node_id=args.node, attempt=attempt)
    result_path = (args.result or workspace / "result.json").resolve()
    if not result_path.is_file():
        raise BridgeError(EXIT_NOT_READY, "result_missing", path=str(result_path))
    result = read_json(result_path)
    if not isinstance(result, dict):
        raise BridgeError(EXIT_INVALID, "result_rejected", node_id=args.node, errors=["result must be a JSON object"])
    errors = rt.validate_agent_result(result, task["task_id"])
    artifacts: list[dict[str, Any]] = []
    refs = result.get("artifact_refs")
    for index, ref in enumerate(refs if isinstance(refs, list) else []):
        if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
            errors.append(f"artifact_refs[{index}] needs path and sha256")
            continue
        path = Path(str(ref["path"]))
        path = (path if path.is_absolute() else workspace / path).resolve()
        record = {"node_id": args.node, "path": str(path), "sha256": str(ref["sha256"]),
                  "kind": str(ref.get("semantic_type") or ref.get("kind") or "artifact")}
        if not path.is_relative_to(workspace):
            errors.append(f"artifact escaped private workspace: {path}")
        elif not path.is_file() or sha256_file(path) != ref["sha256"]:
            errors.append(f"artifact missing or hash mismatch: {path}")
        elif rt.redact(record) != record:
            # The event log redacts secret-looking strings; a mangled path could never be re-verified.
            errors.append(f"artifact path would be altered by event-log redaction, rename it: {path}")
        else:
            artifacts.append(record)
    declared = result.get("native_agent_id")
    worker = args.worker or declared
    if not worker or not isinstance(worker, str):
        errors.append("worker identity required: pass --worker <native agent id | root>")
    elif declared and args.worker and declared != args.worker:
        errors.append(f"--worker {args.worker} contradicts result.native_agent_id {declared}")
    elif run.degraded_mode(snapshot) and worker not in ROOT_WORKERS:
        errors.append("run is in single-agent degraded mode; worker must be root")
    if errors:  # nothing recorded: the worker may fix result.json and resubmit before the deadline
        raise BridgeError(EXIT_INVALID, "result_rejected", node_id=args.node, errors=errors)
    late = lease_overdue(state)
    if late and not args.accept_late:
        raise BridgeError(EXIT_NOT_READY, "lease_expired", node_id=args.node, lease_expires_at=state["lease_expires_at"],
                          hint="controller decides: `submit --accept-late` (audited) or `expire --node`")
    if late:
        run.event("late_result_accepted", {"node_id": args.node, "attempt": attempt, "lease_expires_at": state["lease_expires_at"]})
        run.event("metric_recorded", {"name": "late_result_accepted", "value": 1})
    run.store.record_result(run.run_id, args.node, result, worker)
    for artifact in artifacts:
        run.event("artifact_recorded", artifact)
    if result["status"] in {"succeeded", "degraded"}:
        node_status = "succeeded"
        run.store.set_node_status(run.run_id, args.node, node_status, attempts=attempt, thread_id=worker)
    elif result["status"] == "blocked":
        node_status = "awaiting_input"
        run.store.set_node_status(run.run_id, args.node, node_status, attempts=attempt, thread_id=worker)
        questions, seen = [], set()
        for question in snapshot["pending_questions"] + normalize_questions(args.node, result["questions"]):
            key = rt.canonical_json(question)
            if key not in seen and len(questions) < MAX_QUESTIONS:
                questions.append(question)
                seen.add(key)
        run.event("questions_aggregated", {"questions": questions}, actor="scheduler")
        if snapshot["status"] == "running":
            run.store.set_run_status(run.run_id, "awaiting_user", degraded=bool(snapshot["degraded"]))
    else:
        error = "; ".join(map(str, result.get("errors", []))) or "worker reported failure"
        node_status = "retry_scheduled" if node.get("idempotent") and attempt < 2 else "failed"
        run.store.set_node_status(run.run_id, args.node, node_status, attempts=attempt, error=error)
        if node_status == "retry_scheduled":
            run.event("metric_recorded", {"name": "retry", "value": 1})
    propagate_skips(run)
    after = overview(run)
    return {"ok": True, "node_id": args.node, "node_status": node_status, "result_status": result["status"],
            "attempt": attempt, "worker": worker, "late": late, "artifacts_recorded": len(artifacts), **after,
            "next": "answer" if after["run_status"] == "awaiting_user" else ("finalize" if after["complete"] else "claim")}


def cmd_expire(args: argparse.Namespace) -> dict[str, Any]:
    """Explicitly give up on overdue leases (retry once if idempotent, else fail)."""
    run = Run(args.run_dir)
    states = run.node_states()
    targets = [args.node] if args.node else [node_id for node_id, state in states.items() if state["status"] in IN_FLIGHT and lease_overdue(state)]
    nodes = {node["node_id"]: node for node in run.graph["nodes"]}
    for node_id in targets:  # validate everything before changing anything
        state = states.get(node_id)
        if not state or state["status"] not in IN_FLIGHT:
            raise BridgeError(EXIT_NOT_READY, "node_not_in_flight", node_id=node_id)
        if not lease_overdue(state) and not args.force:
            raise BridgeError(EXIT_NOT_READY, "lease_still_valid", node_id=node_id, lease_expires_at=state["lease_expires_at"])
    outcome: dict[str, str] = {}
    for node_id in targets:
        state = states[node_id]
        status = "retry_scheduled" if nodes[node_id].get("idempotent") and state["attempts"] < 2 else "failed"
        run.store.set_node_status(run.run_id, node_id, status, attempts=state["attempts"],
                                  error=f"hard timeout after {nodes[node_id]['hard_timeout_seconds']} seconds (wall clock)")
        run.event("metric_recorded", {"name": "hard_timeout", "value": 1})
        outcome[node_id] = status
    propagate_skips(run)
    after = overview(run)
    return {"ok": True, "expired": outcome, **after,
            "next": "finalize" if after["complete"] and after["run_status"] == "running" else "claim"}


def cmd_answer(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] != "awaiting_user":
        raise BridgeError(EXIT_NOT_READY, "run_not_awaiting_user", run_status=snapshot["status"])
    if not args.source.strip():
        raise BridgeError(EXIT_PERMISSION, "answer_needs_source")
    run.event("user_input_recorded", {"answers": read_json(args.file), "source": args.source}, actor="user")
    run.store.set_run_status(run.run_id, "running", degraded=bool(snapshot["degraded"]))
    return {"ok": True, **overview(run), "next": "claim"}


def build_report(run: Run, snapshot: dict[str, Any]) -> dict[str, Any]:
    events = run.store.events(run.run_id)
    graph = run.graph
    late = {event["payload"]["node_id"] for event in events if event["kind"] == "late_result_accepted"}
    artifacts = [event["payload"] for event in events if event["kind"] == "artifact_recorded"]
    finalized = [event["payload"] for event in events if event["kind"] == FINALIZED_EVENT]
    reasons = finalized[-1]["degraded_reasons"] if finalized else []
    workspaces = {node["node_id"]: run.workspace(node) for node in graph["nodes"]}
    hashes_ok = all(Path(item["path"]).is_file() and sha256_file(Path(item["path"])) == item["sha256"] for item in artifacts)
    private_ok = all(
        item.get("node_id") in workspaces and Path(item["path"]).resolve().is_relative_to(workspaces[item["node_id"]])
        for item in artifacts
    )
    try:
        contract = read_json(run.dir / "requirement.json")
        requirement_valid = isinstance(contract, dict) and not rt.validate_requirement(contract)
        requirement_unchanged = isinstance(contract, dict) and rt.hash_json(contract) == snapshot["contract_hash"]
    except (OSError, ValueError):
        requirement_valid = requirement_unchanged = False
    workers = sorted({node["thread_id"] for node in snapshot["nodes"] if node["thread_id"]})
    return {
        "schema_version": "RunReportV2", "run_id": run.run_id, "final_status": snapshot["status"],
        "graph_version": snapshot["graph_version"], "degraded": bool(snapshot["degraded"]), "degraded_reasons": reasons,
        "replans_used": snapshot["replan_count"], "executor": {"kind": "native_file_bridge", **plugin_info()},
        "native_agents": [worker for worker in workers if worker not in ROOT_WORKERS],
        "nodes": [{
            "node_id": node["node_id"], "status": node["status"], "attempts": node["attempts"],
            "worker": node["thread_id"], "thread_id": node["thread_id"],
            "result_status": (node["result"] or {}).get("status"), "late_accepted": node["node_id"] in late,
            "errors": [node["last_error"]] if node["last_error"] else [],
        } for node in snapshot["nodes"]],
        "artifacts": artifacts,
        "approvals": [{"gate": item["gate"], "decision": item["decision"], "recorded_at": item["recorded_at"]}
                      for item in snapshot["approvals"]],
        "validation": {"requirement_valid": requirement_valid, "requirement_unchanged_since_init": requirement_unchanged,
                       "graph_valid": not rt.validate_graph(graph),
                       "artifact_hashes_valid": hashes_ok, "private_node_outputs_valid": private_ok},
        "metrics": snapshot["metrics"],
        "not_claimed": "This report proves scheduler bookkeeping only; it does not certify creative quality or user approval.",
    }


def write_outputs(run: Run) -> dict[str, Any]:
    snapshot = run.snapshot()
    write_json(run.dir / "snapshot.json", snapshot)
    run.store.export(run.run_id, run.dir / "audit.json")
    report = build_report(run, snapshot)
    write_json(run.dir / "run_report.json", report)
    return report


def cmd_finalize(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] == "running":
        propagate_skips(run)
        state = overview(run)
        if not state["complete"]:
            raise BridgeError(EXIT_NOT_READY, "run_incomplete", ready=state["ready"], in_flight=state["in_flight"], overdue=state["overdue"])
        snapshot, reasons = run.snapshot(), []
        done = [node for node in snapshot["nodes"] if node["status"] == "succeeded"]
        if run.degraded_mode(snapshot):
            reasons.append("single_agent_serial_execution")
        if any((node["result"] or {}).get("status") == "degraded" for node in done):
            reasons.append("node_result_degraded")
        if len(snapshot["nodes"]) > 1 and done and all(node["thread_id"] in ROOT_WORKERS for node in done):
            reasons.append("no_independent_native_worker")
        if any(node["status"] in DEAD for node in snapshot["nodes"]):
            final = "failed"
        else:
            final = "degraded_pending_acceptance" if reasons else args.completion_status
        run.store.set_run_status(run.run_id, final, degraded=bool(reasons))
        # Reasons live in the event log so later re-exports (accept, re-finalize) keep them.
        run.event(FINALIZED_EVENT, {"final_status": final, "degraded_reasons": reasons})
    elif snapshot["status"] in {"awaiting_initial_confirmation", "awaiting_user"}:
        raise BridgeError(EXIT_NOT_READY, "run_not_finalizable", run_status=snapshot["status"])
    report = write_outputs(run)
    status = report["final_status"]
    return {"ok": True, "run_id": run.run_id, "run_status": status, "degraded": report["degraded"],
            "degraded_reasons": report["degraded_reasons"], "validation": report["validation"],
            "report": str(run.dir / "run_report.json"),
            "next": "accept (needs explicit user acceptance)" if status in {"proposed", "degraded_pending_acceptance"} else None}


def cmd_accept(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] not in {"proposed", "degraded_pending_acceptance"}:
        raise BridgeError(EXIT_NOT_READY, "run_not_acceptable", run_status=snapshot["status"])
    if not args.text.strip() or not args.source.strip():
        raise BridgeError(EXIT_PERMISSION, "acceptance_needs_user_text_and_source")
    run.store.record_approval(run.run_id, "final", "approved", {"text": args.text, "source": args.source,
                                                                 "accepted_degraded": bool(snapshot["degraded"])})
    run.store.set_run_status(run.run_id, "approved", degraded=bool(snapshot["degraded"]))  # keep the flag sticky
    return cmd_finalize(args)


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    return {"ok": True, **overview(Run(args.run_dir))}


def cmd_cancel(args: argparse.Namespace) -> dict[str, Any]:
    run = Run(args.run_dir)
    snapshot = run.snapshot()
    if snapshot["status"] in {"approved", "failed", "canceled"}:
        raise BridgeError(EXIT_NOT_READY, "run_already_terminal", run_status=snapshot["status"])
    run.event("cancel_reason_recorded", {"reason": args.reason})
    run.store.cancel(run.run_id)
    if snapshot["degraded"]:  # the runtime's cancel() resets the flag; restore it for the audit trail
        run.store.set_run_status(run.run_id, "canceled", degraded=True)
    write_outputs(run)
    return {"ok": True, **overview(run), "report": str(run.dir / "run_report.json")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, run_dir: bool = True) -> argparse.ArgumentParser:
        command = commands.add_parser(name)
        command.set_defaults(handler=handler, run_dir=None)
        if run_dir:
            command.add_argument("--run-dir", type=Path, required=True)
        return command

    add("doctor", cmd_doctor, run_dir=False)
    add("init", cmd_init).add_argument("--scope")
    approve = add("approve", cmd_approve)
    approve.add_argument("--text")
    approve.add_argument("--source")
    approve.add_argument("--scope")
    approve.add_argument("--from-contract", action="store_true", help="quote requirement.confirmations[-1].text")
    claim = add("claim", cmd_claim)
    claim.add_argument("--max", type=int, help="host agent slots available right now")
    claim.add_argument("--single-agent", action="store_true", help="no native agents: serial fallback, run becomes degraded (sticky)")
    claim.add_argument("--reason")
    submit = add("submit", cmd_submit)
    submit.add_argument("--node", required=True)
    submit.add_argument("--worker", help="native agent id, or `root` when the controller did the work")
    submit.add_argument("--result", type=Path)
    submit.add_argument("--accept-late", action="store_true")
    expire = add("expire", cmd_expire)
    expire.add_argument("--node")
    expire.add_argument("--force", action="store_true")
    answer = add("answer", cmd_answer)
    answer.add_argument("--file", type=Path, required=True)
    answer.add_argument("--source", required=True)
    finalize = add("finalize", cmd_finalize)
    finalize.add_argument("--completion-status", choices=["proposed", "awaiting_spec_confirmation"], default="proposed")
    accept = add("accept", cmd_accept)
    accept.add_argument("--text", required=True)
    accept.add_argument("--source", required=True)
    accept.set_defaults(completion_status="proposed")
    add("status", cmd_status)
    add("cancel", cmd_cancel).add_argument("--reason", required=True)
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_dir is None:
        return args.handler(args)
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise BridgeError(EXIT_INVALID, "run_dir_not_found", path=str(run_dir))
    with run_lock(run_dir):
        return args.handler(args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload, code = dispatch(args), 0
    except BridgeError as exc:
        payload, code = exc.payload, exc.code
    except PermissionError as exc:
        payload, code = {"ok": False, "error": str(exc)}, EXIT_PERMISSION
    except (OSError, ValueError, KeyError, TypeError, AttributeError, rt.LegacySchemaError) as exc:
        payload, code = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, EXIT_INVALID
    except sqlite3.Error as exc:
        payload, code = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, EXIT_INTERNAL
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
