#!/usr/bin/env python3
"""Deterministic local index, retrieval, plan validation, and skill audit."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any

import yaml
from agentskills_core import (
    ResourceNotFoundError,
    SkillNotFoundError,
    SkillProvider,
    SkillRegistry,
    split_frontmatter,
)
from agentskills_retrieval import LexicalSelector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator_runtime import (  # noqa: E402
    validate_graph as validate_execution_graph,
    validate_requirement as validate_requirement_contract,
)


CATALOG_VERSION = "SkillCatalogV1"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
BUILTIN_SEMANTIC_TYPES = {
    "ai-script-breakdown": {
        "inputs": ["screenplay_source"],
        "outputs": ["screenplay_breakdown_v1"],
    },
    "screenplay-concept-director": {
        "inputs": ["screenplay_source", "screenplay_breakdown_v1", "user_reference_image"],
        "outputs": [
            "asset_catalog_v1",
            "asset_context_snapshot_v1",
            "visual_asset_requirement_v1",
            "creative_position_v1",
        ],
    },
    "image-prompt-team": {
        "inputs": ["visual_asset_requirement_v1"],
        "outputs": ["visual_prompt_spec_v1", "image_prompt_package_v2", "run_report_v2"],
    },
    "evidence-guardian": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["agent_result_v1", "evidence_ledger_v1"]},
    "prompt-architect": {"inputs": ["agent_task_v1", "evidence_ledger_v1"], "outputs": ["agent_result_v1", "platform_neutral_prompt_draft_v1"]},
    "visual-production-critic": {"inputs": ["agent_task_v1", "platform_neutral_prompt_draft_v1"], "outputs": ["agent_result_v1", "production_critique_v1"]},
    "adversarial-reviewer": {"inputs": ["agent_task_v1", "platform_neutral_prompt_draft_v1"], "outputs": ["agent_result_v1", "adversarial_review_v1"]},
    "synthesis-adjudicator": {"inputs": ["agent_task_v1", "production_critique_v1", "adversarial_review_v1"], "outputs": ["agent_result_v1", "adjudicated_prompt_v1"]},
    "visual-brief-director": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "visual-hierarchy-director": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "design-language-director": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "motif-curator": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "color-light-director": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "camera-composition-director": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "character-asset-designer": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "environment-asset-designer": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "prop-asset-designer": {"inputs": ["agent_task_v1", "visual_asset_requirement_v1"], "outputs": ["expert_position_v1"]},
    "visual-spec-assembler": {"inputs": ["agent_task_v1", "expert_position_v1"], "outputs": ["visual_prompt_spec_v1"]},
    "prompt-salience-editor": {"inputs": ["agent_task_v1", "visual_prompt_spec_v1"], "outputs": ["prompt_salience_plan_v1"]},
    "openai-image-prompt-compiler": {"inputs": ["agent_task_v1", "visual_prompt_spec_v1", "prompt_salience_plan_v1"], "outputs": ["image_prompt_package_v2"]},
    "reference-role-director": {"inputs": ["agent_task_v1", "user_reference_image"], "outputs": ["reference_role_v1"]},
}
ASCII_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items() if key.lower() not in {"secret", "password", "token", "api_key"}}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result[:8000]
    return value


def parse_skill(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    errors: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {}, "", [f"read_error: {exc}"]
    if not raw.startswith("---"):
        return {}, raw, ["missing_yaml_frontmatter"]
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", raw, re.DOTALL)
    if not match:
        return {}, raw, ["unterminated_yaml_frontmatter"]
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return {}, raw, [f"yaml_error: {exc}"]
    if not isinstance(meta, dict):
        return {}, raw, ["frontmatter_must_be_mapping"]
    body = raw[match.end():].strip()
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        errors.append("missing_or_invalid_name")
    if not isinstance(description, str) or not description.strip():
        errors.append("missing_or_invalid_description")
    return meta, body, errors


def words(text: str) -> list[str]:
    return [token.lower() for token in ASCII_TOKEN.findall(text)]


def listify(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def infer_enrichment(meta: dict[str, Any], body: str) -> dict[str, Any]:
    name = str(meta.get("name", ""))
    description = str(meta.get("description", ""))
    description_lower = f"{name}\n{description}".lower()
    lower = f"{description_lower}\n{body[:16000]}".lower()
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    tags = listify(metadata.get("tags"))
    headings = re.findall(r"^#{1,3}\s+(.+)$", body, flags=re.MULTILINE)
    capabilities = sorted(set(tags + [name] + headings[:8]))
    when_to_use = listify(meta.get("when_to_use"))
    when_not_to_use = listify(meta.get("when_not_to_use"))

    permissions: list[str] = []
    if re.search(r"\b(web|browser|http|api|network|github|download|upload)\b", lower):
        permissions.append("network")
    if re.search(r"\b(read|inspect|scan|open)\b.*\b(file|folder|directory|repo)", lower):
        permissions.append("filesystem:read")
    if re.search(r"\b(create|edit|write|patch|save|generate)\b.*\b(file|folder|directory|repo|artifact)", lower):
        permissions.append("filesystem:write")
    if re.search(r"\b(shell|terminal|command|subprocess|bash|zsh|powershell|script)\b", lower):
        permissions.append("process:execute")
    if re.search(r"\b(send|publish|deploy|post|upload|install|purchase|pay|delete)\b", description_lower):
        permissions.append("external:write")

    side_effects: list[str] = []
    for label, pattern in {
        "installs software": r"\binstall(?:s|ation|ing)?\b",
        "writes files": r"\b(create|edit|write|patch|save|generate)\b.*\b(file|artifact|repo)",
        "sends or publishes externally": r"\b(send|publish|deploy|post|upload)\b",
        "destructive change": r"\b(delete|remove|overwrite|drop|truncate|reset --hard)\b",
        "financial transaction": r"\b(pay|purchase|buy|trade|charge)\b",
    }.items():
        haystack = lower if label == "destructive change" else description_lower
        if re.search(pattern, haystack):
            side_effects.append(label)

    # Safety sections often discuss forbidden destructive actions. Only elevate
    # that signal when executable-looking destructive syntax is present.
    if "destructive change" in side_effects and not re.search(
        r"(?i)(rm\s+-rf|reset\s+--hard|drop\s+table|rmtree\(|unlink\(|delete\s+(?:files?|records?|data|repository))",
        lower,
    ):
        side_effects.remove("destructive change")

    if any(effect in side_effects for effect in ("destructive change", "financial transaction")):
        risk = "critical"
    elif "sends or publishes externally" in side_effects or "external:write" in permissions:
        risk = "high"
    elif "process:execute" in permissions or "filesystem:write" in permissions:
        risk = "medium"
    else:
        risk = "low"

    registered = BUILTIN_SEMANTIC_TYPES.get(name, {})
    inputs = listify(metadata.get("input_types")) + list(registered.get("inputs", []))
    outputs = listify(metadata.get("output_types")) + list(registered.get("outputs", []))
    for item_type, pattern in {
        "image": r"\b(image|photo|png|jpg|jpeg)\b",
        "video": r"\b(video|mp4|movie)\b",
        "document": r"\b(document|docx|word|markdown|text)\b",
        "spreadsheet": r"\b(spreadsheet|xlsx|csv|table)\b",
        "code": r"\b(code|repository|codebase|source)\b",
        "url": r"\b(url|website|web page)\b",
    }.items():
        if re.search(pattern, lower):
            inputs.append(item_type)
            outputs.append(item_type)
    if re.search(r"\b(report|analysis|feedback|review|summary)\b", lower):
        outputs.append("report")

    confidence = 0.45
    if tags:
        confidence += 0.15
    if when_to_use or when_not_to_use:
        confidence += 0.15
    if re.search(r"(?im)^##?\s+(inputs?|outputs?|permissions?|safety|workflow)", body):
        confidence += 0.15
    if meta.get("allowed-tools"):
        confidence += 0.1
    confidence = min(confidence, 0.95)
    return {
        "capabilities": capabilities,
        "when_to_use": when_to_use,
        "when_not_to_use": when_not_to_use,
        "inputs": sorted(set(inputs)),
        "outputs": sorted(set(outputs)),
        "dependencies": listify(metadata.get("dependencies")),
        "permissions": sorted(set(permissions + listify(meta.get("allowed-tools")))),
        "side_effects": side_effects,
        "risk_level": risk,
        "confidence": round(confidence, 2),
        "needs_review": confidence < 0.7 or risk in {"high", "critical"},
        "manual_override": False,
    }


def default_roots(project: Path, plugin_cache: Path | None = None) -> list[dict[str, str]]:
    user = Path.home()
    plugin_root = plugin_cache or (Path(os.environ.get("CODEX_HOME", user / ".codex")) / "plugins" / "cache")
    return [
        {"path": str(project / ".codex" / "skills"), "scope": "project", "source": "project-codex"},
        {"path": str(project / ".agents" / "skills"), "scope": "project", "source": "project-agents"},
        {"path": str(user / ".codex" / "skills"), "scope": "user", "source": "user-codex"},
        {"path": str(user / ".agents" / "skills"), "scope": "user", "source": "user-agents"},
        {"path": str(plugin_root), "scope": "plugin", "source": "plugin-cache"},
    ]


def find_skill_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((path for path in root.rglob("SKILL.md") if path.is_file()), key=lambda p: str(p).casefold())


def load_overrides(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Override file must be a YAML mapping")
    skills = payload.get("skills", payload)
    if not isinstance(skills, dict):
        raise ValueError("Override 'skills' must be a mapping")
    return {str(name): value for name, value in skills.items() if isinstance(value, dict)}


def build_catalog(
    project: Path,
    output: Path,
    overrides_path: Path | None = None,
    plugin_cache: Path | None = None,
    roots: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    if output.is_file():
        try:
            previous_payload = json.loads(output.read_text(encoding="utf-8"))
            previous = {item["name"]: item for item in previous_payload.get("skills", [])}
        except (OSError, ValueError, KeyError):
            previous = {}
    overrides = load_overrides(overrides_path)
    root_specs = roots or default_roots(project.resolve(), plugin_cache)
    active: dict[str, dict[str, Any]] = {}
    shadowed: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    refreshed = 0
    reused = 0

    for priority, spec in enumerate(root_specs):
        root = Path(spec["path"]).expanduser().resolve()
        for skill_file in find_skill_files(root):
            meta, body, errors = parse_skill(skill_file)
            if errors:
                invalid.append({"path": str(skill_file), "source": spec["source"], "errors": errors})
                continue
            name = meta["name"].strip()
            record = {
                "name": name,
                "description": meta["description"].strip(),
                "path": str(skill_file),
                "skill_root": str(skill_file.parent),
                "scope": spec["scope"],
                "source": spec["source"],
                "priority": priority,
                "content_hash": sha256_file(skill_file),
                "version": meta.get("version") or (meta.get("metadata", {}) if isinstance(meta.get("metadata"), dict) else {}).get("version"),
                "frontmatter": meta,
            }
            if name in active:
                record["shadowed_by"] = active[name]["path"]
                shadowed.append(record)
                continue
            old = previous.get(name)
            if old and old.get("content_hash") == record["content_hash"]:
                for key in ("capabilities", "when_to_use", "when_not_to_use", "inputs", "outputs", "dependencies", "permissions", "side_effects", "risk_level", "confidence", "needs_review", "manual_override"):
                    if key in old:
                        record[key] = old[key]
                reused += 1
            else:
                record.update(infer_enrichment(meta, body))
                refreshed += 1
            if name in overrides:
                for key, value in overrides[name].items():
                    if key not in {"name", "path", "content_hash", "source", "scope", "priority"}:
                        record[key] = value
                record["manual_override"] = True
                record["needs_review"] = False
            active[name] = record

    catalog = {
        "schema_version": CATALOG_VERSION,
        "generated_at": utc_now(),
        "project_root": str(project.resolve()),
        "roots": root_specs,
        "stats": {"active": len(active), "shadowed": len(shadowed), "invalid": len(invalid), "refreshed": refreshed, "reused": reused},
        "skills": sorted(active.values(), key=lambda item: item["name"]),
        "shadowed": shadowed,
        "invalid": invalid,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(redact(catalog), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return catalog


class ResolvedPathProvider(SkillProvider):
    supports_resource_listing = True
    supports_discovery = True

    def __init__(self, records: dict[str, dict[str, Any]]) -> None:
        self.records = records

    def _root(self, skill_id: str) -> Path:
        try:
            return Path(self.records[skill_id]["skill_root"]).resolve()
        except KeyError as exc:
            raise SkillNotFoundError(f"Unknown skill: {skill_id}") from exc

    def _resource(self, skill_id: str, kind: str, name: str) -> Path:
        root = self._root(skill_id)
        path = (root / kind / PurePosixPath(name)).resolve()
        if not path.is_relative_to(root / kind) or not path.is_file():
            raise ResourceNotFoundError(f"Unknown {kind} resource {name!r} in {skill_id}")
        return path

    async def get_metadata(self, skill_id: str) -> dict[str, Any]:
        if skill_id not in self.records:
            raise SkillNotFoundError(f"Unknown skill: {skill_id}")
        return dict(self.records[skill_id]["frontmatter"])

    async def get_body(self, skill_id: str) -> str:
        path = self._root(skill_id) / "SKILL.md"
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        return body

    async def get_script(self, skill_id: str, name: str) -> bytes:
        return self._resource(skill_id, "scripts", name).read_bytes()

    async def get_asset(self, skill_id: str, name: str) -> bytes:
        return self._resource(skill_id, "assets", name).read_bytes()

    async def get_reference(self, skill_id: str, name: str) -> bytes:
        return self._resource(skill_id, "references", name).read_bytes()

    async def list_resources(self, skill_id: str) -> dict[str, list[str]]:
        root = self._root(skill_id)
        result: dict[str, list[str]] = {}
        for kind in ("references", "scripts", "assets"):
            base = root / kind
            result[kind] = sorted(str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()) if base.is_dir() else []
        return result

    async def discover(self) -> list[str]:
        return sorted(self.records)


async def search_catalog(catalog_path: Path, query: str, limit: int = 12, max_risk: str = "critical", deny_permissions: list[str] | None = None, require_outputs: list[str] | None = None, require_inputs: list[str] | None = None) -> dict[str, Any]:
    if not ASCII_TOKEN.search(query):
        raise ValueError("The retrieval query needs English/ASCII capability terms derived from RequirementContractV2.")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    source_records = {record["name"]: record for record in catalog.get("skills", [])}
    records: dict[str, dict[str, Any]] = {}
    for original_name, original in source_records.items():
        sdk_id = re.sub(r"[^a-z0-9]+", "-", original_name.lower()).strip("-") or "skill"
        if sdk_id in records:
            sdk_id = f"{sdk_id}-{hashlib.sha256(original_name.encode()).hexdigest()[:8]}"
        record = dict(original)
        metadata = original.get("frontmatter", {}) if isinstance(original.get("frontmatter"), dict) else {}
        sdk_metadata: dict[str, Any] = {"name": sdk_id, "description": original["description"]}
        if isinstance(metadata.get("metadata"), dict):
            sdk_metadata["metadata"] = metadata["metadata"]
        for key in ("when_to_use", "when_not_to_use"):
            values = original.get(key, metadata.get(key))
            if isinstance(values, list) and all(isinstance(item, str) for item in values):
                sdk_metadata[key] = values
        record["frontmatter"] = sdk_metadata
        record["original_name"] = original_name
        records[sdk_id] = record
    provider = ResolvedPathProvider(records)
    registry = SkillRegistry()
    failures: list[dict[str, str]] = []
    for name in sorted(records):
        try:
            await registry.register(name, provider)
        except ValueError as exc:
            failures.append({"name": name, "error": str(exc)})
    selector = LexicalSelector(registry)
    selection = await selector.select(query, limit=max(limit * 3, limit))
    denied = set(deny_permissions or [])
    required = set(require_outputs or [])
    required_input_types = set(require_inputs or [])
    candidates = []
    filtered = []
    for scored in selection.selected:
        record = records[scored.skill_id]
        reasons = []
        if RISK_ORDER.get(record.get("risk_level", "critical"), 3) > RISK_ORDER[max_risk]:
            reasons.append(f"risk>{max_risk}")
        if denied.intersection(record.get("permissions", [])):
            reasons.append("denied_permission")
        if required and not required.intersection(record.get("outputs", [])):
            reasons.append("output_incompatible")
        known_inputs = set(record.get("inputs", []))
        if required_input_types and known_inputs and not required_input_types.intersection(known_inputs):
            reasons.append("input_incompatible")
        item = {
            "name": record["original_name"],
            "score": round(scored.score, 6),
            "path": record["path"],
            "description": record["description"],
            "risk_level": record.get("risk_level"),
            "permissions": record.get("permissions", []),
            "side_effects": record.get("side_effects", []),
            "outputs": record.get("outputs", []),
            "confidence": record.get("confidence"),
            "needs_review": record.get("needs_review", False),
        }
        if reasons:
            item["filter_reasons"] = reasons
            filtered.append(item)
        elif len(candidates) < limit:
            candidates.append(item)
    return {"query": query, "considered": selection.considered, "candidates": candidates, "filtered": filtered, "registration_failures": failures}


def validate_requirement(contract: dict[str, Any]) -> list[str]:
    return validate_requirement_contract(contract)


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "run_id", "final_status", "graph_version", "degraded", "replans_used", "nodes", "artifacts", "validation", "metrics", "conclusion"}
    missing = sorted(required - report.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if report.get("schema_version") != "RunReportV2":
        errors.append("schema_version must be RunReportV2")
    if report.get("replans_used") not in (0, 1):
        errors.append("replans_used must be 0 or 1")
    statuses = {"pending", "ready", "leased", "running", "awaiting_input", "retry_scheduled", "succeeded", "failed", "skipped", "invalidated", "canceled"}
    nodes = report.get("nodes", [])
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        return errors
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] must be an object")
            continue
        node_id = node.get("node_id")
        if not node_id or node_id in seen:
            errors.append(f"nodes[{index}] has missing or duplicate id")
        if node_id:
            seen.add(node_id)
        if node.get("status") not in statuses:
            errors.append(f"{node_id} has invalid status")
        if not isinstance(node.get("attempts"), int) or not 0 <= node["attempts"] <= 2:
            errors.append(f"{node_id} attempts must be between 0 and 2")
        if not isinstance(node.get("errors", []), list):
            errors.append(f"{node_id}.errors must be a list")
    return sorted(set(errors))


def validate_plan(plan: dict[str, Any]) -> list[str]:
    return validate_execution_graph(plan)


def audit_skill(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    findings: list[dict[str, str]] = []
    files: list[dict[str, Any]] = []
    if not (root / "SKILL.md").is_file():
        findings.append({"severity": "critical", "code": "missing_skill_md", "path": str(root)})
    text_extensions = {".md", ".txt", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".rb", ".ps1"}
    patterns = {
        "network_call": re.compile(r"(?i)\b(requests\.|urllib|curl\s|wget\s|fetch\(|https?://|socket\.)"),
        "subprocess": re.compile(r"(?i)\b(subprocess|os\.system|child_process|exec\(|spawn\()"),
        "destructive": re.compile(r"(?i)\b(rm\s+-rf|shutil\.rmtree|drop\s+table|git\s+reset\s+--hard|unlink\()"),
        "credential_access": re.compile(r"(?i)\b(os\.environ|getenv|keychain|credential|\.ssh|\.aws)\b"),
    }
    if not root.is_dir():
        return {"root": str(root), "safe_to_review": False, "findings": findings, "files": []}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            findings.append({"severity": "high", "code": "hidden_path", "path": str(relative)})
        if path.is_symlink():
            target = path.resolve()
            severity = "critical" if not target.is_relative_to(root) else "high"
            findings.append({"severity": severity, "code": "symlink", "path": str(relative), "target": str(target)})
            continue
        if not path.is_file():
            continue
        mode = path.stat().st_mode
        executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        item = {"path": str(relative), "sha256": sha256_file(path), "size": path.stat().st_size, "executable": executable}
        files.append(item)
        if executable:
            findings.append({"severity": "high", "code": "executable_file", "path": str(relative)})
        if path.suffix.lower() in text_extensions and path.stat().st_size <= 2_000_000:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeError:
                findings.append({"severity": "medium", "code": "undecodable_text", "path": str(relative)})
                continue
            for code, pattern in patterns.items():
                if pattern.search(content):
                    severity = "critical" if code == "destructive" else "high"
                    findings.append({"severity": severity, "code": code, "path": str(relative)})
        elif path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}:
            findings.append({"severity": "medium", "code": "unrecognized_binary", "path": str(relative)})
    max_severity = max((RISK_ORDER.get(item["severity"], 0) for item in findings), default=0)
    return {
        "root": str(root),
        "audited_at": utc_now(),
        "safe_to_review": max_severity < RISK_ORDER["critical"],
        "safe_to_execute": not findings,
        "findings": findings,
        "files": files,
    }


async def evaluate(catalog_path: Path, gold_path: Path, limit: int = 3) -> dict[str, Any]:
    tasks = json.loads(gold_path.read_text(encoding="utf-8"))
    results = []
    top1_hits = 0
    recalled = 0
    expected_total = 0
    no_match_hits = 0
    no_match_total = 0
    for task in tasks:
        result = await search_catalog(catalog_path, task["retrieval_query_en"], limit=max(limit, 3))
        names = [item["name"] for item in result["candidates"]]
        raw_expected = task.get("expected_skills", task.get("expected_skill"))
        expected = raw_expected if isinstance(raw_expected, list) else ([raw_expected] if raw_expected else [])
        if expected:
            expected_total += len(expected)
            recalled += len(set(expected).intersection(names[:limit]))
            task_top1 = bool(names and names[0] in expected)
        else:
            no_match_total += 1
            task_top1 = not names
            no_match_hits += task_top1
        top1_hits += task_top1
        results.append({"id": task["id"], "expected": expected, "selected": names[:limit], "top1": task_top1, "recalled": sorted(set(expected).intersection(names[:limit]))})
    count = len(tasks)
    return {
        "tasks": count,
        "top1": top1_hits / count if count else 0,
        f"top{limit}_recall": recalled / expected_total if expected_total else 0,
        "no_match_accuracy": no_match_hits / no_match_total if no_match_total else None,
        "results": results,
    }


def write_json(payload: Any, output: Path | None = None) -> None:
    text = json.dumps(redact(payload), indent=2, ensure_ascii=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Build or incrementally refresh the catalog.")
    index.add_argument("--project", type=Path, required=True)
    index.add_argument("--output", type=Path, required=True)
    index.add_argument("--overrides", type=Path)
    index.add_argument("--plugin-cache", type=Path)
    search = commands.add_parser("search", help="BM25-retrieve skills from a catalog.")
    search.add_argument("--catalog", type=Path, required=True)
    query_source = search.add_mutually_exclusive_group(required=True)
    query_source.add_argument("--query")
    query_source.add_argument("--contract", type=Path)
    search.add_argument("--limit", type=int, default=12)
    search.add_argument("--max-risk", choices=list(RISK_ORDER), default="critical")
    search.add_argument("--deny-permission", action="append", default=[])
    search.add_argument("--require-input", action="append", default=[])
    search.add_argument("--require-output", action="append", default=[])
    search.add_argument("--output", type=Path)
    interface = commands.add_parser("validate-interface", help="Validate a stable orchestrator interface.")
    interface.add_argument("--type", choices=["requirement", "plan", "report"], required=True)
    interface.add_argument("--file", type=Path, required=True)
    plan = commands.add_parser("validate-plan", help="Validate ExecutionGraphV2 bindings and DAG.")
    plan.add_argument("--plan", type=Path, required=True)
    audit = commands.add_parser("audit-skill", help="Statically audit an external skill tree.")
    audit.add_argument("--path", type=Path, required=True)
    audit.add_argument("--output", type=Path)
    evaluation = commands.add_parser("eval", help="Measure routing recall against a gold set.")
    evaluation.add_argument("--catalog", type=Path, required=True)
    evaluation.add_argument("--gold", type=Path, required=True)
    evaluation.add_argument("--limit", type=int, default=3)
    evaluation.add_argument("--output", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "index":
            payload = build_catalog(args.project, args.output, args.overrides, args.plugin_cache)
            write_json(payload["stats"])
        elif args.command == "search":
            query = args.query
            required_inputs = list(args.require_input)
            required_outputs = list(args.require_output)
            denied_permissions = list(args.deny_permission)
            max_risk = args.max_risk
            if args.contract:
                contract = json.loads(args.contract.read_text(encoding="utf-8"))
                errors = validate_requirement(contract)
                if errors:
                    raise ValueError("Invalid RequirementContractV2: " + "; ".join(errors))
                query = " ".join((contract.get("goal", ""), contract.get("target_platform", ""), contract.get("asset_input", {}).get("asset_type", "")))
                required_inputs.append("visual_asset_requirement_v1")
                required_outputs.append("image_prompt_package_v2")
            payload = asyncio.run(search_catalog(args.catalog, query, args.limit, max_risk, denied_permissions, required_outputs, required_inputs))
            write_json(payload, args.output)
        elif args.command == "validate-interface":
            document = json.loads(args.file.read_text(encoding="utf-8"))
            validators = {"requirement": validate_requirement, "plan": validate_plan, "report": validate_report}
            errors = validators[args.type](document)
            write_json({"valid": not errors, "errors": errors})
            return 0 if not errors else 1
        elif args.command == "validate-plan":
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            errors = validate_plan(plan)
            write_json({"valid": not errors, "errors": errors})
            return 0 if not errors else 1
        elif args.command == "audit-skill":
            payload = audit_skill(args.path)
            write_json(payload, args.output)
            return 0 if payload["safe_to_review"] else 1
        elif args.command == "eval":
            payload = asyncio.run(evaluate(args.catalog, args.gold, args.limit))
            write_json(payload, args.output)
            return 0 if payload.get("top3_recall", 0) >= 0.9 and payload["top1"] >= 0.8 else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        write_json({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
