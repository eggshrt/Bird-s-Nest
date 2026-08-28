#!/usr/bin/env python3
"""Skill Orchestrator V2 deterministic runtime and Codex App Server bridge.

The append-only event log is authoritative. Mutable run/node tables are query
projections and can be rebuilt with ``replay``.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import uuid


SCHEMA_VERSION = 2
RUN_STATUSES = {
    "draft", "awaiting_initial_confirmation", "running", "awaiting_user",
    "awaiting_spec_confirmation", "proposed", "degraded_pending_acceptance",
    "approved", "failed", "canceled",
}
NODE_STATUSES = {
    "pending", "ready", "leased", "running", "awaiting_input", "retry_scheduled",
    "succeeded", "failed", "skipped", "invalidated", "canceled",
}
RESULT_STATUSES = {"succeeded", "failed", "blocked", "degraded"}
FORBIDDEN_EXTERNAL_EFFECTS = {"external_write", "publish", "payment", "destructive"}
SECRET_KEYS = {"secret", "password", "token", "api_key", "dispatcher_key"}
RUN_TRANSITIONS = {
    "draft": {"awaiting_initial_confirmation", "canceled"},
    "awaiting_initial_confirmation": {"running", "canceled"},
    "running": {"awaiting_user", "awaiting_spec_confirmation", "proposed", "degraded_pending_acceptance", "failed", "canceled"},
    "awaiting_user": {"running", "failed", "canceled"},
    "awaiting_spec_confirmation": {"running", "canceled"},
    "proposed": {"approved", "canceled"},
    "degraded_pending_acceptance": {"approved", "canceled"},
    "approved": set(), "failed": set(), "canceled": set(),
}
NODE_TRANSITIONS = {
    "pending": {"ready", "leased", "skipped", "invalidated", "canceled"},
    "ready": {"leased", "skipped", "invalidated", "canceled"},
    "leased": {"running", "retry_scheduled", "failed", "canceled"},
    "running": {"running", "awaiting_input", "retry_scheduled", "succeeded", "failed", "invalidated", "canceled"},
    "awaiting_input": {"leased", "running", "invalidated", "canceled"},
    "retry_scheduled": {"leased", "invalidated", "canceled"},
    "succeeded": {"invalidated"}, "failed": {"invalidated"}, "skipped": {"invalidated"},
    "invalidated": {"pending", "canceled"}, "canceled": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items() if key.lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+", "[REDACTED]", value)
        value = re.sub(r"(?:sk|gh[pousr])-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
        return value[:12000]
    return value


def validate_collaboration_context(context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if context.get("schema_version") != "CollaborationContextV1":
        errors.append("schema_version must be CollaborationContextV1")
    quadrants = ("shared_known", "user_context_gaps", "agent_added_context", "joint_unknown_hypotheses")
    for quadrant in quadrants:
        items = context.get(quadrant)
        if not isinstance(items, list):
            errors.append(f"{quadrant} must be a list")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not all(item.get(key) for key in ("id", "statement", "provenance", "status")):
                errors.append(f"{quadrant}[{index}] is incomplete")
    return sorted(set(errors))


def validate_requirement(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "goal", "asset_input", "audience", "target_platform",
        "in_scope", "out_of_scope", "constraints", "acceptance_criteria",
        "collaboration_context", "confirmations", "open_questions",
    }
    missing = sorted(required - contract.keys())
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
    if contract.get("schema_version") != "RequirementContractV2":
        errors.append("schema_version must be RequirementContractV2")
    asset = contract.get("asset_input")
    if not isinstance(asset, dict) or not all(asset.get(key) for key in ("asset_id", "requirement_path", "requirement_hash")):
        errors.append("asset_input must identify one asset, path, and hash")
    if contract.get("open_questions"):
        errors.append("open_questions must be empty before graph confirmation")
    errors.extend(validate_collaboration_context(contract.get("collaboration_context", {})))
    return sorted(set(errors))


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("node_id", ""))


def validate_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("schema_version") != "ExecutionGraphV2":
        errors.append("schema_version must be ExecutionGraphV2")
    if graph.get("max_concurrency", 0) not in (1, 2, 3):
        errors.append("max_concurrency must be between 1 and 3")
    if graph.get("max_replans") not in (0, 1):
        errors.append("max_replans must be 0 or 1")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["nodes must be a non-empty list"]
    by_id: dict[str, dict[str, Any]] = {}
    objectives: dict[str, str] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] must be an object")
            continue
        node_id = _node_id(node)
        if not node_id or node_id in by_id:
            errors.append(f"nodes[{index}] has missing or duplicate node_id")
            continue
        by_id[node_id] = node
        for field in (
            "role_skill", "objective", "input_bindings", "output_schema", "depends_on",
            "execution_mode", "idempotent", "soft_timeout_seconds", "hard_timeout_seconds",
            "permissions", "side_effects", "risk", "verification",
        ):
            if field not in node:
                errors.append(f"{node_id} missing {field}")
        if node.get("execution_mode") not in {"serial", "parallel"}:
            errors.append(f"{node_id} has invalid execution_mode")
        if not isinstance(node.get("idempotent"), bool):
            errors.append(f"{node_id}.idempotent must be boolean")
        if not isinstance(node.get("hard_timeout_seconds"), int) or node.get("hard_timeout_seconds", 0) <= 0:
            errors.append(f"{node_id}.hard_timeout_seconds must be positive")
        if node.get("soft_timeout_seconds", 0) >= node.get("hard_timeout_seconds", 0):
            errors.append(f"{node_id} soft timeout must be below hard timeout")
        effects = set(node.get("side_effects", [])) if isinstance(node.get("side_effects"), list) else set()
        if effects.intersection(FORBIDDEN_EXTERNAL_EFFECTS):
            errors.append(f"{node_id} requests forbidden v0.4 side effects")
        normalized = re.sub(r"\W+", " ", str(node.get("objective", "")).lower()).strip()
        if normalized and normalized in objectives:
            errors.append(f"responsibility overlap: {node_id} and {objectives[normalized]}")
        objectives[normalized] = node_id
    for node_id, node in by_id.items():
        dependencies = node.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{node_id}.depends_on must be a list")
            continue
        for dependency in dependencies:
            if dependency not in by_id:
                errors.append(f"{node_id} references missing dependency {dependency}")
        for binding in node.get("input_bindings", []):
            if not isinstance(binding, dict) or not binding.get("from"):
                errors.append(f"{node_id} has invalid input binding")
                continue
            source = str(binding["from"])
            if source.startswith(("requirement.", "context.")):
                continue
            source_id = source.split(".", 1)[0]
            if source_id not in dependencies:
                errors.append(f"{node_id} binding {source} is not a declared dependency")
    state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        if state.get(node_id) == 1:
            errors.append(f"cycle detected at {node_id}")
            return
        if state.get(node_id) == 2:
            return
        state[node_id] = 1
        for dependency in by_id[node_id].get("depends_on", []):
            if dependency in by_id:
                visit(dependency)
        state[node_id] = 2

    for node_id in by_id:
        visit(node_id)
    return sorted(set(errors))


def topological_order(graph: dict[str, Any]) -> list[str]:
    errors = validate_graph(graph)
    if errors:
        raise ValueError("Invalid ExecutionGraphV2: " + "; ".join(errors))
    nodes = {_node_id(node): node for node in graph["nodes"]}
    indegree = {node_id: len(node.get("depends_on", [])) for node_id, node in nodes.items()}
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for node_id, node in nodes.items():
            if current in node.get("depends_on", []):
                indegree[node_id] -= 1
                if indegree[node_id] == 0:
                    ready.append(node_id)
                    ready.sort()
    if len(order) != len(nodes):
        raise ValueError("ExecutionGraphV2 contains a cycle")
    return order


def descendants(graph: dict[str, Any], roots: set[str]) -> set[str]:
    affected = set(roots)
    changed = True
    while changed:
        changed = False
        for node in graph.get("nodes", []):
            node_id = _node_id(node)
            if node_id not in affected and affected.intersection(node.get("depends_on", [])):
                affected.add(node_id)
                changed = True
    return affected


def apply_graph_patch(graph: dict[str, Any], patch: dict[str, Any], confirmed: bool = False) -> tuple[dict[str, Any], set[str]]:
    """Apply a validated semantic patch; never silently repair the graph."""
    if patch.get("schema_version") != "DagPatchV1":
        raise ValueError("schema_version must be DagPatchV1")
    if patch.get("base_graph_version") != graph.get("graph_version"):
        raise ValueError("DagPatchV1 base_graph_version is stale")
    impact = patch.get("semantic_impact")
    if impact not in {"low", "high", "contract_change"}:
        raise ValueError("invalid semantic_impact")
    if impact == "contract_change":
        raise ValueError("contract changes must freeze this run and derive a new run")
    if (patch.get("confirmation_required") or impact == "high") and not confirmed:
        raise PermissionError("DAG patch needs explicit confirmation")
    candidate = deepcopy(graph)
    by_id = {_node_id(node): node for node in candidate["nodes"]}
    changed: set[str] = set()
    for operation in patch.get("operations", []):
        op = operation.get("op")
        if op == "add_node":
            node = operation.get("node", {})
            node_id = _node_id(node)
            if not node_id or node_id in by_id:
                raise ValueError("add_node needs a unique node_id")
            candidate["nodes"].append(node)
            by_id[node_id] = node
            changed.add(node_id)
        elif op == "replace_node":
            node = operation.get("node", {})
            node_id = _node_id(node)
            if node_id not in by_id:
                raise ValueError(f"replace_node references missing {node_id}")
            candidate["nodes"] = [node if _node_id(item) == node_id else item for item in candidate["nodes"]]
            by_id[node_id] = node
            changed.add(node_id)
        elif op == "add_dependency":
            node_id, dependency = operation.get("node_id"), operation.get("depends_on")
            if node_id not in by_id or dependency not in by_id:
                raise ValueError("add_dependency references missing node")
            if dependency not in by_id[node_id]["depends_on"]:
                by_id[node_id]["depends_on"].append(dependency)
            changed.add(node_id)
        else:
            raise ValueError(f"unsupported DAG patch operation: {op}")
    candidate["graph_version"] = int(graph.get("graph_version", 1)) + 1
    errors = validate_graph(candidate)
    if errors:
        raise ValueError("patched graph is invalid: " + "; ".join(errors))
    invalidated = descendants(candidate, changed)
    declared = set(patch.get("invalidated_nodes", []))
    if declared and declared != invalidated:
        raise ValueError("invalidated_nodes does not match affected descendants")
    return candidate, invalidated


def validate_agent_result(result: dict[str, Any], task_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if result.get("schema_version") != "AgentResultV1":
        errors.append("schema_version must be AgentResultV1")
    if task_id and result.get("task_id") != task_id:
        errors.append("task_id does not match dispatch")
    if result.get("status") not in RESULT_STATUSES:
        errors.append("invalid AgentResultV1 status")
    for field in ("claims", "evidence_refs", "artifact_refs", "conflicts", "questions", "errors"):
        if not isinstance(result.get(field), list):
            errors.append(f"{field} must be a list")
    if len(canonical_json(result)) > 1_000_000:
        errors.append("AgentResultV1 embeds too much raw data")
    return sorted(set(errors))


def sign_task(task: dict[str, Any], dispatcher_key: str) -> str:
    unsigned = {key: value for key, value in task.items() if key != "dispatcher_signature"}
    return hmac.new(dispatcher_key.encode(), canonical_json(unsigned).encode(), hashlib.sha256).hexdigest()


class LegacySchemaError(RuntimeError):
    pass


class EventStore:
    """Append events and maintain disposable SQLite projections."""

    def __init__(self, db_path: Path) -> None:
        self.path = db_path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "schema_meta" not in tables:
                raise LegacySchemaError("Legacy orchestrator database detected; v0.4 refuses import or in-place migration")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, seq INTEGER NOT NULL,
                    created_at TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL,
                    graph_version INTEGER NOT NULL, correlation_id TEXT, causation_id TEXT,
                    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    UNIQUE(run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, graph_version INTEGER NOT NULL,
                    contract_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    degraded INTEGER NOT NULL DEFAULT 0, replan_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_versions(
                    run_id TEXT NOT NULL, version INTEGER NOT NULL, graph_json TEXT NOT NULL,
                    graph_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, version)
                );
                CREATE TABLE IF NOT EXISTS nodes(
                    run_id TEXT NOT NULL, node_id TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, lease_owner TEXT, lease_expires_at TEXT,
                    thread_id TEXT, last_error TEXT, result_json TEXT,
                    PRIMARY KEY(run_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS approvals(
                    run_id TEXT NOT NULL, gate TEXT NOT NULL, decision TEXT NOT NULL,
                    recorded_at TEXT NOT NULL, details_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, gate, recorded_at)
                );
                CREATE TABLE IF NOT EXISTS artifacts(
                    run_id TEXT NOT NULL, node_id TEXT, path TEXT NOT NULL, sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, path)
                );
                CREATE TABLE IF NOT EXISTS metrics(
                    run_id TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                """
            )
            versions = [row[0] for row in connection.execute("SELECT version FROM schema_meta")]
            if versions and versions != [SCHEMA_VERSION]:
                raise LegacySchemaError(f"Unsupported database schema {versions}; expected {SCHEMA_VERSION}")
            if not versions:
                connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))

    def append(
        self, run_id: str, kind: str, payload: dict[str, Any], actor: str = "scheduler",
        graph_version: int = 1, correlation_id: str | None = None,
        causation_id: str | None = None, event_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            seq = connection.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            created = utc_now()
            safe_payload = redact(payload)
            payload_json = canonical_json(safe_payload)
            event = {
                "schema_version": "RunEventV1", "event_id": event_id or str(uuid.uuid4()),
                "run_id": run_id, "seq": seq, "created_at": created, "kind": kind,
                "actor": actor, "graph_version": graph_version,
                "correlation_id": correlation_id, "causation_id": causation_id,
                "payload": safe_payload, "payload_hash": hashlib.sha256(payload_json.encode()).hexdigest(),
            }
            connection.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (event["event_id"], run_id, seq, created, kind, actor, graph_version,
                 correlation_id, causation_id, payload_json, event["payload_hash"]),
            )
            self._project(connection, event)
            return event

    def _project(self, connection: sqlite3.Connection, event: dict[str, Any]) -> None:
        run_id, kind, payload, now = event["run_id"], event["kind"], event["payload"], event["created_at"]
        if kind == "run_created":
            connection.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, payload["status"], payload.get("graph_version", 1), payload["contract_hash"],
                 now, now, 0, 0, canonical_json(payload.get("metadata", {}))),
            )
        elif kind == "run_status_changed":
            connection.execute(
                "UPDATE runs SET status=?, degraded=?, updated_at=? WHERE run_id=?",
                (payload["status"], int(payload.get("degraded", False)), now, run_id),
            )
        elif kind == "graph_registered":
            graph = payload["graph"]
            version = payload["version"]
            connection.execute(
                "INSERT OR REPLACE INTO graph_versions VALUES (?,?,?,?,?)",
                (run_id, version, canonical_json(graph), hash_json(graph), now),
            )
            connection.execute("UPDATE runs SET graph_version=?, updated_at=? WHERE run_id=?", (version, now, run_id))
            for node in graph["nodes"]:
                connection.execute(
                    "INSERT OR IGNORE INTO nodes(run_id,node_id,status) VALUES (?,?,?)",
                    (run_id, node["node_id"], "pending"),
                )
        elif kind == "node_status_changed":
            connection.execute(
                "UPDATE nodes SET status=?, attempts=?, lease_owner=?, lease_expires_at=?, thread_id=COALESCE(?,thread_id), last_error=? WHERE run_id=? AND node_id=?",
                (payload["status"], payload.get("attempts", 0), payload.get("lease_owner"),
                 payload.get("lease_expires_at"), payload.get("thread_id"), payload.get("error"),
                 run_id, payload["node_id"]),
            )
        elif kind == "node_result_recorded":
            connection.execute(
                "UPDATE nodes SET result_json=?, thread_id=COALESCE(?,thread_id) WHERE run_id=? AND node_id=?",
                (canonical_json(payload["result"]), payload.get("thread_id"), run_id, payload["node_id"]),
            )
        elif kind == "approval_recorded":
            connection.execute(
                "INSERT INTO approvals VALUES (?,?,?,?,?)",
                (run_id, payload["gate"], payload["decision"], now, canonical_json(payload.get("details", {}))),
            )
        elif kind == "replan_recorded":
            connection.execute("UPDATE runs SET replan_count=replan_count+1, updated_at=? WHERE run_id=?", (now, run_id))
        elif kind == "artifact_recorded":
            connection.execute(
                "INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?)",
                (run_id, payload.get("node_id"), payload["path"], payload["sha256"], payload["kind"], now),
            )
        elif kind == "metric_recorded":
            connection.execute("INSERT INTO metrics VALUES (?,?,?,?)", (run_id, payload["name"], payload["value"], now))

    def create_run(self, contract: dict[str, Any], graph: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
        requirement_errors = validate_requirement(contract)
        graph_errors = validate_graph(graph)
        if requirement_errors or graph_errors:
            raise ValueError("; ".join(requirement_errors + graph_errors))
        run_id = f"run-{uuid.uuid4()}"
        self.append(run_id, "run_created", {
            "status": "awaiting_initial_confirmation", "graph_version": 1,
            "contract_hash": hash_json(contract), "metadata": metadata or {},
        })
        self.append(run_id, "graph_registered", {"version": 1, "graph": graph})
        return run_id

    def register_patch(self, run_id: str, patch: dict[str, Any], confirmed: bool = False, automatic: bool = False) -> set[str]:
        snapshot = self.snapshot(run_id)
        if automatic and snapshot["replan_count"] >= 1:
            raise ValueError("automatic replan limit reached")
        graph, invalidated = apply_graph_patch(self.graph(run_id), patch, confirmed=confirmed)
        if automatic:
            self.append(run_id, "replan_recorded", {"patch": patch}, graph_version=snapshot["graph_version"])
        self.append(run_id, "graph_registered", {"version": graph["graph_version"], "graph": graph}, graph_version=graph["graph_version"])
        for node_id in sorted(invalidated):
            self.set_node_status(run_id, node_id, "invalidated", attempts=0)
            self.set_node_status(run_id, node_id, "pending", attempts=0)
        return invalidated

    def set_run_status(self, run_id: str, status: str, degraded: bool = False) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"Invalid run status: {status}")
        current = self.snapshot(run_id)["status"]
        if status != current and status not in RUN_TRANSITIONS[current]:
            raise ValueError(f"Invalid run transition: {current} -> {status}")
        self.append(run_id, "run_status_changed", {"status": status, "degraded": degraded}, graph_version=self.graph_version(run_id))

    def set_node_status(self, run_id: str, node_id: str, status: str, **details: Any) -> None:
        if status not in NODE_STATUSES:
            raise ValueError(f"Invalid node status: {status}")
        current_node = next((item for item in self.snapshot(run_id)["nodes"] if item["node_id"] == node_id), None)
        if not current_node:
            raise KeyError(f"Unknown node: {node_id}")
        current = current_node["status"]
        if status != current and status not in NODE_TRANSITIONS[current]:
            raise ValueError(f"Invalid node transition for {node_id}: {current} -> {status}")
        self.append(run_id, "node_status_changed", {"node_id": node_id, "status": status, **details}, graph_version=self.graph_version(run_id))

    def record_result(self, run_id: str, node_id: str, result: dict[str, Any], thread_id: str | None = None) -> None:
        self.append(run_id, "node_result_recorded", {"node_id": node_id, "result": result, "thread_id": thread_id}, graph_version=self.graph_version(run_id))

    def renew_lease(self, run_id: str, node_id: str, owner: str, attempts: int, ttl_seconds: int = 60) -> None:
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        self.set_node_status(
            run_id, node_id, "running", attempts=attempts,
            lease_owner=owner, lease_expires_at=expiry,
        )

    def recover_expired_leases(self, run_id: str) -> list[str]:
        """Recover work abandoned by a dead scheduler without retrying non-idempotent work."""
        graph = {_node_id(node): node for node in self.graph(run_id)["nodes"]}
        now = utc_now()
        recovered: list[str] = []
        for node in self.snapshot(run_id)["nodes"]:
            expiry = node.get("lease_expires_at")
            if node["status"] not in {"leased", "running"} or not expiry or expiry >= now:
                continue
            definition = graph[node["node_id"]]
            if definition.get("idempotent") and node["attempts"] < 2:
                status = "retry_scheduled"
            else:
                status = "failed"
            self.set_node_status(
                run_id, node["node_id"], status, attempts=node["attempts"],
                error="orphaned lease recovered after scheduler interruption",
            )
            self.append(run_id, "metric_recorded", {"name": "orphan_lease_recovered", "value": 1})
            recovered.append(node["node_id"])
        return recovered

    def record_approval(self, run_id: str, gate: str, decision: str, details: dict[str, Any] | None = None) -> None:
        self.append(run_id, "approval_recorded", {"gate": gate, "decision": decision, "details": details or {}}, actor="user", graph_version=self.graph_version(run_id))

    def graph_version(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT graph_version FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return int(row[0])

    def graph(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT graph_json FROM graph_versions WHERE run_id=? ORDER BY version DESC LIMIT 1", (run_id,)
            ).fetchone()
        if not row:
            raise KeyError(run_id)
        return json.loads(row[0])

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            run = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not run:
                raise KeyError(run_id)
            nodes = connection.execute("SELECT * FROM nodes WHERE run_id=? ORDER BY node_id", (run_id,)).fetchall()
            approvals = connection.execute("SELECT * FROM approvals WHERE run_id=? ORDER BY recorded_at", (run_id,)).fetchall()
            metrics = connection.execute("SELECT name,value,recorded_at FROM metrics WHERE run_id=?", (run_id,)).fetchall()
            question_event = connection.execute("SELECT seq,payload_json FROM events WHERE run_id=? AND kind='questions_aggregated' ORDER BY seq DESC LIMIT 1", (run_id,)).fetchone()
            answer_event = connection.execute("SELECT seq FROM events WHERE run_id=? AND kind='user_input_recorded' ORDER BY seq DESC LIMIT 1", (run_id,)).fetchone()
        payload = dict(run)
        payload["metadata"] = json.loads(payload.pop("metadata_json"))
        payload["nodes"] = []
        for row in nodes:
            node = dict(row)
            node["result"] = json.loads(node.pop("result_json")) if node.get("result_json") else None
            payload["nodes"].append(node)
        payload["approvals"] = [dict(row) for row in approvals]
        payload["metrics"] = [dict(row) for row in metrics]
        payload["pending_questions"] = (
            json.loads(question_event["payload_json"]).get("questions", [])
            if question_event and (not answer_event or question_event["seq"] > answer_event["seq"]) else []
        )
        return redact(payload)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def replay(self, run_id: str) -> None:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
            if not rows:
                raise KeyError(run_id)
            connection.execute("DELETE FROM metrics WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM artifacts WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM approvals WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM nodes WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM graph_versions WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            for row in rows:
                event = dict(row)
                event["payload"] = json.loads(event.pop("payload_json"))
                self._project(connection, event)

    def cancel(self, run_id: str) -> None:
        snapshot = self.snapshot(run_id)
        if snapshot["status"] in {"approved", "failed", "canceled"}:
            raise ValueError(f"terminal run {snapshot['status']} cannot be canceled")
        for node in snapshot["nodes"]:
            if node["status"] not in {"succeeded", "failed", "skipped", "canceled"}:
                self.set_node_status(run_id, node["node_id"], "canceled", attempts=node["attempts"])
        self.set_run_status(run_id, "canceled")

    def export(self, run_id: str, output: Path) -> dict[str, Any]:
        payload = {"schema_version": "RunAuditExportV1", "run": self.snapshot(run_id), "events": self.events(run_id)}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def prune(self, run_id: str | None = None, before: str | None = None) -> int:
        if not run_id and not before:
            raise ValueError("prune requires --run-id or --before")
        with self._lock, self._connect() as connection:
            if run_id:
                ids = [run_id]
            else:
                ids = [row[0] for row in connection.execute("SELECT run_id FROM runs WHERE created_at < ?", (before,))]
            for candidate in ids:
                for table in ("metrics", "artifacts", "approvals", "nodes", "graph_versions", "runs", "events"):
                    connection.execute(f"DELETE FROM {table} WHERE run_id=?", (candidate,))
            return len(ids)


class Scheduler:
    def __init__(self, store: EventStore, concurrency: int = 3, lease_ttl_seconds: int = 60, heartbeat_seconds: int = 20) -> None:
        self.store = store
        self.concurrency = max(1, min(3, concurrency))
        self.lease_ttl_seconds = lease_ttl_seconds
        self.heartbeat_seconds = max(1, min(heartbeat_seconds, max(1, lease_ttl_seconds // 2)))

    def execute(
        self, run_id: str,
        executor: Callable[[dict[str, Any], dict[str, dict[str, Any]], int], tuple[dict[str, Any], str | None]],
        completion_status: str = "proposed",
    ) -> dict[str, Any]:
        if completion_status not in {"awaiting_spec_confirmation", "proposed"}:
            raise ValueError("unsupported scheduler completion_status")
        graph = self.store.graph(run_id)
        errors = validate_graph(graph)
        if errors:
            raise ValueError("Invalid graph: " + "; ".join(errors))
        self.store.recover_expired_leases(run_id)
        current = self.store.snapshot(run_id)
        if not any(item["gate"] == "initial" and item["decision"] == "confirmed" for item in current["approvals"]):
            raise PermissionError("Initial execution confirmation is required")
        self.store.set_run_status(run_id, "running")
        nodes = {node["node_id"]: node for node in graph["nodes"]}
        results = {item["node_id"]: item["result"] for item in current["nodes"] if item["result"]}
        completed = {item["node_id"] for item in current["nodes"] if item["status"] == "succeeded"}
        failed = {item["node_id"] for item in current["nodes"] if item["status"] in {"failed", "skipped", "canceled"}}
        degraded = False
        started = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=min(self.concurrency, graph.get("max_concurrency", 3)))
        try:
            while len(completed) + len(failed) < len(nodes):
                pending = [node_id for node_id in topological_order(graph) if node_id not in completed | failed]
                for node_id in list(pending):
                    if any(dependency in failed for dependency in nodes[node_id].get("depends_on", [])):
                        self.store.set_node_status(run_id, node_id, "skipped", error="failed dependency")
                        failed.add(node_id)
                ready = [
                    node_id for node_id in pending if node_id not in failed
                    and set(nodes[node_id].get("depends_on", [])).issubset(completed)
                ][: self.concurrency]
                if not ready:
                    if len(completed) + len(failed) < len(nodes):
                        self.store.append(run_id, "metric_recorded", {"name": "deadlock_detected", "value": 1})
                        self.store.set_run_status(run_id, "failed")
                        raise RuntimeError("No ready nodes remain; dependency deadlock detected")
                    break
                futures: dict[Any, tuple[str, int, float]] = {}
                for node_id in ready:
                    snapshot_node = next(item for item in self.store.snapshot(run_id)["nodes"] if item["node_id"] == node_id)
                    attempt = snapshot_node["attempts"] if snapshot_node["status"] == "awaiting_input" else snapshot_node["attempts"] + 1
                    attempt = max(1, attempt)
                    lease_expiry = (datetime.now(timezone.utc) + timedelta(seconds=self.lease_ttl_seconds)).isoformat()
                    self.store.set_node_status(run_id, node_id, "leased", attempts=attempt, lease_owner="local-scheduler", lease_expires_at=lease_expiry)
                    self.store.set_node_status(run_id, node_id, "running", attempts=attempt, lease_owner="local-scheduler", lease_expires_at=lease_expiry)
                    dependency_results = {dep: results[dep] for dep in nodes[node_id].get("depends_on", []) if dep in results}
                    futures[pool.submit(executor, nodes[node_id], dependency_results, attempt)] = (node_id, attempt, time.monotonic())
                done: set[Any] = set()
                pending_futures = set(futures)
                timed_out: set[Any] = set()
                while pending_futures:
                    newly_done, pending_futures = wait(pending_futures, timeout=self.heartbeat_seconds)
                    done.update(newly_done)
                    if self.store.snapshot(run_id)["status"] == "canceled":
                        cancel_method = getattr(executor, "cancel", None)
                        if callable(cancel_method):
                            for future in pending_futures:
                                cancel_method(futures[future][0])
                        wait(pending_futures, timeout=30)
                        for future in pending_futures:
                            future.cancel()
                        return self.store.snapshot(run_id)
                    now_monotonic = time.monotonic()
                    expired = {
                        future for future in pending_futures
                        if now_monotonic - futures[future][2] >= nodes[futures[future][0]]["hard_timeout_seconds"]
                    }
                    pending_futures.difference_update(expired)
                    for future in expired:
                        node_id, attempt, _ = futures[future]
                        future.cancel()
                    timed_out.update(expired)
                    for future in pending_futures:
                        node_id, attempt, _ = futures[future]
                        self.store.renew_lease(run_id, node_id, "local-scheduler", attempt, self.lease_ttl_seconds)
                for future in timed_out:
                    node_id, attempt, _ = futures[future]
                    future.cancel()
                    error = f"hard timeout after {nodes[node_id]['hard_timeout_seconds']} seconds"
                    self.store.set_node_status(run_id, node_id, "failed", attempts=attempt, error=error)
                    failed.add(node_id)
                    self.store.append(run_id, "metric_recorded", {"name": "hard_timeout", "value": 1})
                blocked_questions: list[dict[str, Any]] = []
                for future in done:
                    node_id, attempt, _ = futures[future]
                    try:
                        result, thread_id = future.result()
                        result_errors = validate_agent_result(result)
                        if result_errors:
                            raise ValueError("; ".join(result_errors))
                    except Exception as exc:  # executor failures become controlled node failures
                        result = {
                            "schema_version": "AgentResultV1", "task_id": f"{run_id}:{node_id}:{attempt}",
                            "status": "failed", "summary": "Agent execution failed", "claims": [],
                            "evidence_refs": [], "artifact_refs": [], "conflicts": [], "questions": [],
                            "errors": [str(exc)], "metrics": {},
                        }
                        thread_id = None
                    self.store.record_result(run_id, node_id, result, thread_id)
                    if result["status"] in {"succeeded", "degraded"}:
                        degraded = degraded or result["status"] == "degraded"
                        self.store.set_node_status(run_id, node_id, "succeeded", attempts=attempt, thread_id=thread_id)
                        completed.add(node_id)
                        results[node_id] = result
                    elif result["status"] == "blocked":
                        self.store.set_node_status(run_id, node_id, "awaiting_input", attempts=attempt, thread_id=thread_id)
                        blocked_questions.extend(item for item in result.get("questions", []) if isinstance(item, dict))
                    elif nodes[node_id].get("idempotent") and attempt < 2:
                        self.store.set_node_status(run_id, node_id, "retry_scheduled", attempts=attempt, error="; ".join(result.get("errors", [])))
                        self.store.append(run_id, "metric_recorded", {"name": "retry", "value": 1})
                    else:
                        self.store.set_node_status(run_id, node_id, "failed", attempts=attempt, error="; ".join(result.get("errors", [])))
                        failed.add(node_id)
                if blocked_questions:
                    unique_questions: list[dict[str, Any]] = []
                    seen_questions: set[str] = set()
                    for question in blocked_questions:
                        key = canonical_json(question)
                        if key not in seen_questions:
                            unique_questions.append(question)
                            seen_questions.add(key)
                        if len(unique_questions) == 3:
                            break
                    self.store.append(run_id, "questions_aggregated", {"questions": unique_questions})
                    self.store.set_run_status(run_id, "awaiting_user")
                    return self.store.snapshot(run_id)
            elapsed = time.monotonic() - started
            self.store.append(run_id, "metric_recorded", {"name": "scheduling_latency_seconds", "value": elapsed})
            if failed:
                self.store.set_run_status(run_id, "failed", degraded=degraded)
            else:
                terminal_status = "degraded_pending_acceptance" if degraded else completion_status
                self.store.set_run_status(run_id, terminal_status, degraded=degraded)
            return self.store.snapshot(run_id)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


class AppServerClient:
    """Minimal concurrent JSON-RPC client for ``codex app-server --stdio``."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or [os.environ.get("CODEX_BIN", "codex"), "app-server", "--stdio"]
        self.process: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._next_id = 1
        self._completed: dict[str, dict[str, Any]] = {}
        self._condition = threading.Condition()
        self._reader: threading.Thread | None = None

    def start(self) -> None:
        if self.process:
            return
        self.process = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self.request("initialize", {
            "clientInfo": {"name": "skill-orchestrator", "version": "0.4.0"},
            "capabilities": {"experimentalApi": True},
        })
        self.notify("initialized", {})

    def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in message and ("result" in message or "error" in message):
                pending = self._pending.get(int(message["id"]))
                if pending:
                    pending.put(message)
            elif message.get("method") == "turn/completed":
                params = message.get("params", {})
                with self._condition:
                    self._completed[str(params.get("threadId"))] = params
                    self._condition.notify_all()

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30) -> Any:
        self.start() if not self.process and method != "initialize" else None
        with self._write_lock:
            request_id = self._next_id
            self._next_id += 1
            pending: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = pending
            assert self.process and self.process.stdin
            self.process.stdin.write(canonical_json({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}) + "\n")
            self.process.stdin.flush()
        try:
            message = pending.get(timeout=timeout)
        finally:
            self._pending.pop(request_id, None)
        if "error" in message:
            raise RuntimeError(f"App Server {method} failed: {message['error']}")
        return message.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        with self._write_lock:
            assert self.process and self.process.stdin
            self.process.stdin.write(canonical_json({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
            self.process.stdin.flush()

    def read_config(self, cwd: Path) -> dict[str, Any]:
        return self.request("config/read", {"cwd": str(cwd.resolve()), "includeLayers": True})

    def run_agent(
        self, task: dict[str, Any], role_skill: str, cwd: Path, output_schema: dict[str, Any], timeout: int,
        thread_id: str | None = None, on_thread_started: Callable[[str], None] | None = None,
        skill_path: Path | None = None, on_turn_started: Callable[[str, str], None] | None = None,
        sandbox_policy: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str]:
        if thread_id:
            resumed = self.request("thread/resume", {"threadId": thread_id})
            thread_id = resumed["thread"]["id"]
        else:
            started = self.request("thread/start", {
                "cwd": str(cwd.resolve()), "sandbox": "read-only", "approvalPolicy": "never",
                "ephemeral": False,
            })
            thread_id = started["thread"]["id"]
        if on_thread_started:
            on_thread_started(thread_id)
        prompt = (
            f"Use ${role_skill}. This is a dispatcher-signed task. Do not interview the user and do not write files. "
            "Return only AgentResultV1 JSON matching the supplied output schema.\n\n"
            + json.dumps(task, ensure_ascii=False, indent=2)
        )
        inputs: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if skill_path:
            resolved_skill = skill_path.resolve()
            if not resolved_skill.is_file():
                raise FileNotFoundError(f"Role skill not found: {resolved_skill}")
            inputs.append({"type": "skill", "name": role_skill, "path": str(resolved_skill)})
        started_turn = self.request("turn/start", {
            "threadId": thread_id, "input": inputs,
            "outputSchema": output_schema,
            "sandboxPolicy": sandbox_policy or {"type": "readOnly", "access": {"type": "fullAccess"}},
        })
        turn_id = started_turn["turn"]["id"]
        if on_turn_started:
            on_turn_started(thread_id, turn_id)
        deadline = time.monotonic() + timeout
        with self._condition:
            while thread_id not in self._completed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=10)
                    except Exception:
                        pass
                    self._condition.wait(timeout=30)
                    raise TimeoutError(f"Agent thread {thread_id} exceeded {timeout}s")
                self._condition.wait(timeout=min(remaining, 1.0))
            completed = self._completed.pop(thread_id)
        turn = completed.get("turn", {})
        if turn.get("status") != "completed":
            raise RuntimeError(f"Agent turn did not complete: {turn.get('status')}")
        messages = [item.get("text", "") for item in turn.get("items", []) if item.get("type") == "agentMessage"]
        if not messages:
            raise RuntimeError("Agent returned no final message")
        result = json.loads(messages[-1])
        return result, thread_id

    def archive_thread(self, thread_id: str) -> None:
        self.request("thread/archive", {"threadId": thread_id})

    def interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=10)

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def danger_mode_enabled(config_response: dict[str, Any]) -> bool:
    def values(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [item for child in value.values() for item in values(child)]
        if isinstance(value, list):
            return [item for child in value for item in values(child)]
        return [str(value).lower()]
    return any(item in {"danger-full-access", ":danger-full-access", "dangerfullaccess"} for item in values(config_response))


def default_db(project: Path) -> Path:
    return project.resolve() / ".codex" / "skill-orchestrator" / "runtime-v2.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "cancel", "replay"):
        command = commands.add_parser(name)
        command.add_argument("--run-id", required=True)
    export = commands.add_parser("export")
    export.add_argument("--run-id", required=True)
    export.add_argument("--output", type=Path, required=True)
    prune = commands.add_parser("prune")
    prune.add_argument("--run-id")
    prune.add_argument("--before")
    validate = commands.add_parser("validate-graph")
    validate.add_argument("--file", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate-graph":
            errors = validate_graph(json.loads(args.file.read_text(encoding="utf-8")))
            print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        store = EventStore(args.db or default_db(args.project))
        if args.command == "status":
            payload = store.snapshot(args.run_id)
        elif args.command == "cancel":
            store.cancel(args.run_id)
            payload = store.snapshot(args.run_id)
        elif args.command == "replay":
            store.replay(args.run_id)
            payload = store.snapshot(args.run_id)
        elif args.command == "export":
            payload = store.export(args.run_id, args.output)
        elif args.command == "prune":
            payload = {"pruned_runs": store.prune(args.run_id, args.before)}
        else:
            raise ValueError(args.command)
        print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, LegacySchemaError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
