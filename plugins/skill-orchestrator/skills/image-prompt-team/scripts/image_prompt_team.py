#!/usr/bin/env python3
"""Run the recoverable v0.4 single-asset visual prompt team."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any

CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "skill-orchestrator" / "scripts"
sys.path.insert(0, str(CORE_SCRIPTS))
from orchestrator_runtime import (  # noqa: E402
    AppServerClient, EventStore, Scheduler, canonical_json, danger_mode_enabled,
    default_db, hash_json, redact, sign_task, utc_now,
)

PLUGIN_VERSION = "0.4.0"
FORBIDDEN_PACKAGE_KEYS = {
    "negative_prompt", "model_parameters", "model_parameter", "image", "images",
    "image_generation", "generation_settings", "size", "quality", "design_statement",
}
ASSET_TYPES = {"character_master", "location_master", "scene_state", "hero_prop"}
CREATIVE_ROLE_SKILLS = {
    "brief": "visual-brief-director", "hierarchy": "visual-hierarchy-director",
    "language": "design-language-director", "motif": "motif-curator",
    "color_light": "color-light-director", "camera": "camera-composition-director",
}
ASSET_ROLE_SKILLS = {
    "character_master": "character-asset-designer", "location_master": "environment-asset-designer",
    "scene_state": "environment-asset-designer", "hero_prop": "prop-asset-designer",
}
CONTROL_ROLE_SKILLS = {
    "evidence": "evidence-guardian", "assembler": "visual-spec-assembler",
    "production": "visual-production-critic", "adversarial": "adversarial-reviewer",
    "adjudicator": "synthesis-adjudicator", "salience": "prompt-salience-editor",
    "compiler": "openai-image-prompt-compiler",
}
CONDITIONAL_ROLE_SKILLS = {"reference": "reference-role-director"}
ROLE_SKILLS = {**CREATIVE_ROLE_SKILLS, **CONTROL_ROLE_SKILLS, **CONDITIONAL_ROLE_SKILLS}

AGENT_RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "task_id", "status", "summary", "claims", "evidence_refs", "artifact_refs", "conflicts", "questions", "errors", "metrics"],
    "properties": {
        "schema_version": {"const": "AgentResultV1"}, "task_id": {"type": "string"},
        "status": {"enum": ["succeeded", "failed", "blocked", "degraded"]},
        "summary": {"type": "string"}, "claims": {"type": "array", "items": {"type": "object"}},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "artifact_refs": {"type": "array", "items": {"type": "object"}},
        "conflicts": {"type": "array", "items": {"type": "object"}},
        "questions": {"type": "array", "items": {"type": "object"}, "maxItems": 3},
        "errors": {"type": "array", "items": {"type": "string"}}, "metrics": {"type": "object"},
    },
}


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_asset_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            ids.add(child) if key == "asset_id" and isinstance(child, str) else ids.update(collect_asset_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(collect_asset_ids(child))
    return ids


def collect_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key)); keys.update(collect_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(collect_keys(child))
    return keys


def validate_visual_requirement(requirement: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if requirement.get("schema_version") != "VisualAssetRequirementV1":
        errors.append("schema_version must be VisualAssetRequirementV1")
    asset = requirement.get("asset")
    if not isinstance(asset, dict) or not all(asset.get(key) for key in ("asset_id", "asset_type", "name")):
        errors.append("asset must contain asset_id, asset_type, and name")
    elif asset.get("asset_type") not in ASSET_TYPES:
        errors.append("unsupported asset_type")
    if len(collect_asset_ids(requirement)) != 1:
        errors.append("requirement must contain exactly one asset_id")
    if requirement.get("open_questions"):
        errors.append("open_questions must be empty")
    for index, decision in enumerate(requirement.get("high_impact_decisions", [])):
        if decision.get("status") != "accepted":
            errors.append(f"high_impact_decisions[{index}] is not accepted")
    gates = {item.get("gate") for item in requirement.get("confirmations", []) if item.get("confirmed") is True}
    if not {"asset_selection", "design_requirement", "persistence_plan"}.issubset(gates):
        errors.append("all three upstream confirmations are required")
    if isinstance(requirement.get("freshness"), dict) and requirement["freshness"].get("status") not in (None, "fresh"):
        errors.append("requirement baseline is stale")
    for index, evidence in enumerate(requirement.get("evidence", [])):
        if evidence.get("kind") == "fact" and not evidence.get("source_refs"):
            errors.append(f"evidence[{index}] fact has no source_refs")
    forbidden = sorted(collect_keys(requirement).intersection({"prompt", *FORBIDDEN_PACKAGE_KEYS}))
    if forbidden:
        errors.append("upstream requirement contains forbidden downstream fields: " + ", ".join(forbidden))
    return sorted(set(errors))


def validate_position(position: dict[str, Any]) -> list[str]:
    errors = []
    if position.get("schema_version") != "ExpertPositionV1":
        errors.append("schema_version must be ExpertPositionV1")
    for field in ("role", "persona_principle", "recommendation", "priority", "confidence", "change_conditions"):
        if not position.get(field): errors.append(f"{field} is required")
    for field in ("evidence_refs", "objections", "alternative"):
        if not isinstance(position.get(field), list): errors.append(f"{field} must be a list")
    return sorted(set(errors))


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors = []
    if spec.get("schema_version") != "VisualPromptSpecV1": errors.append("schema_version must be VisualPromptSpecV1")
    for field in ("asset_id", "asset_type", "requirement_hash", "intended_use", "framing", "aspect_ratio", "evidence_capsule", "blocks", "visibility_matrix", "invariants", "expert_positions", "spec_confirmation"):
        if spec.get(field) in (None, "", []): errors.append(f"{field} is required")
    if collect_asset_ids(spec) != {spec.get("asset_id")}: errors.append("spec must reference exactly one asset_id")
    required_blocks = {"brief", "hierarchy", "design_language", "motifs", "color_light", "camera_composition", "asset_specific"}
    if not isinstance(spec.get("blocks"), dict) or not required_blocks.issubset(spec["blocks"]): errors.append("spec blocks are incomplete")
    if len(spec.get("expert_positions", [])) < 7: errors.append("all six creative roles and one asset specialist are required")
    for index, position in enumerate(spec.get("expert_positions", [])):
        errors.extend(f"expert_positions[{index}]: {item}" for item in validate_position(position))
    if any(not item.get("visible", False) and item.get("invariant", False) for item in spec.get("visibility_matrix", [])):
        errors.append("an invariant is not observable in the confirmed framing")
    if spec.get("rebuttal_rounds", 0) > 1: errors.append("at most one targeted rebuttal round is allowed")
    if collect_keys(spec).intersection(FORBIDDEN_PACKAGE_KEYS): errors.append("spec contains forbidden generation fields")
    return sorted(set(errors))


def validate_package(package: dict[str, Any]) -> list[str]:
    errors = []
    if package.get("schema_version") != "ImagePromptPackageV2": errors.append("schema_version must be ImagePromptPackageV2")
    if package.get("status") not in {"proposed", "degraded", "approved"}: errors.append("invalid package status")
    for field in ("asset_id", "asset_type", "requirement_hash", "visual_prompt_spec_hash", "generation_prompt", "adapter_profile", "trace"):
        if package.get(field) in (None, "", []): errors.append(f"{field} is required")
    if collect_asset_ids(package) != {package.get("asset_id")}: errors.append("package must reference exactly one asset_id")
    forbidden = collect_keys(package).intersection(FORBIDDEN_PACKAGE_KEYS)
    if forbidden: errors.append("forbidden package fields: " + ", ".join(sorted(forbidden)))
    prompt = package.get("generation_prompt", "")
    if not isinstance(prompt, str) or len(prompt.strip()) < 80: errors.append("generation_prompt is too short to be production-usable")
    if re.search(r"【[^】]+】|^(场景|主体|构图|光线|约束)[:：]", prompt, re.MULTILINE): errors.append("generation_prompt must use unlabeled short paragraphs")
    if len(package.get("trace", {}).get("constraint_clauses", [])) > 3: errors.append("generation_prompt has more than three final constraint clauses")
    return sorted(set(errors))


def spec_content_hash(spec: dict[str, Any]) -> str:
    """Hash creative content while keeping approval timestamps out of identity."""
    content = deepcopy(spec)
    content.pop("status", None)
    content.pop("spec_confirmation", None)
    return hash_json(content)


def build_context(requirement: dict[str, Any]) -> dict[str, Any]:
    shared = [{"id": f"shared-{i:03d}", "statement": item.get("statement", ""), "provenance": item.get("kind", "unknown"), "confidence": "high" if item.get("source_refs") else "medium", "impact": "design", "status": "confirmed", "verification": item.get("source_refs", [])} for i, item in enumerate(requirement.get("evidence", []), 1)]
    return {"schema_version": "CollaborationContextV1", "version": 1, "shared_known": shared, "user_context_gaps": [], "agent_added_context": [{"id": "agent-001", "statement": "OpenAI compiler orders scene, subject, visible details, composition/light, then a few invariants.", "provenance": "OpenAI GPT Image prompting guide", "confidence": "high", "impact": "prompt_structure", "status": "accepted_method", "verification": "gold tests"}], "joint_unknown_hypotheses": []}


def build_contract(requirement: dict[str, Any], path: Path, presentation: dict[str, str]) -> dict[str, Any]:
    asset = requirement["asset"]
    return {"schema_version": "RequirementContractV2", "goal": f"为单一资产 {asset['name']} 编译一条证据约束的 OpenAI 中文母提示词", "asset_input": {"asset_id": asset["asset_id"], "asset_type": asset["asset_type"], "requirement_path": str(path.resolve()), "requirement_hash": file_hash(path)}, "audience": ["视觉开发创作者"], "target_platform": "openai-gpt-image-primary", "in_scope": ["visual_prompt_spec", "single_generation_prompt", "local_audit"], "out_of_scope": ["design_redesign", "negative_prompt", "model_parameters", "image_generation", "external_write"], "constraints": ["single_asset", "Chinese_only", "positive_observable_language", "max_three_final_constraints"], "acceptance_criteria": requirement.get("acceptance_criteria", []), "collaboration_context": build_context(requirement), "presentation": presentation, "confirmations": [], "open_questions": []}


def recommend_presentation(requirement: dict[str, Any]) -> dict[str, str]:
    kind = requirement["asset"]["asset_type"]
    if kind == "character_master": return {"intended_use": "人物母版设计评审", "framing": "全身正面偏三分之四视角，人物完整入画", "aspect_ratio": "2:3竖幅"}
    if kind in {"location_master", "scene_state"}: return {"intended_use": "纯环境场景资产评审", "framing": "中低机位超广角，前中后景三层清楚", "aspect_ratio": "21:9超宽银幕"}
    return {"intended_use": "核心道具资产评审", "framing": "三分之四视角，完整轮廓与操作结构清楚", "aspect_ratio": "4:3横幅"}


def graph_node(node_id: str, role: str, objective: str, deps: list[str], output_type: str, mode: str = "serial") -> dict[str, Any]:
    return {"node_id": node_id, "role_skill": role, "objective": objective, "input_bindings": [{"input": "requirement", "from": "requirement.asset_input"}] + [{"input": dep, "from": f"{dep}.result"} for dep in deps], "output_schema": output_type, "depends_on": deps, "execution_mode": mode, "idempotent": True, "soft_timeout_seconds": 300, "hard_timeout_seconds": 600, "permissions": ["filesystem:read"], "side_effects": [], "risk": "low", "verification": {"method": "schema_evidence_and_single_asset", "expected": output_type}}


def build_graph(requirement: dict[str, Any] | list[Any] | None = None) -> dict[str, Any]:
    if not isinstance(requirement, dict): requirement = {"asset": {"asset_type": "character_master"}, "reference_images": []}
    nodes = [graph_node("evidence", "evidence-guardian", "锁定唯一资产、需求哈希、来源、不可变项与越界风险。", [], "EvidenceCheckV1")]
    nodes.append(graph_node("asset-specialist", ASSET_ROLE_SKILLS[requirement["asset"]["asset_type"]], "给出该资产类型的可见设计立场与制作要求。", ["evidence"], "ExpertPositionV1", "parallel"))
    if requirement.get("reference_images"): nodes.append(graph_node("reference-role", "reference-role-director", "为每张参考图限定唯一职责和不得控制的维度。", ["evidence"], "ReferenceRoleV1", "parallel"))
    shared = ["evidence", "asset-specialist"] + (["reference-role"] if requirement.get("reference_images") else [])
    objectives = {
        "brief": "锁定交付用途、媒介、总体基调和可见目标。",
        "hierarchy": "锁定唯一视觉中心、注意力顺序和信息密度。",
        "language": "锁定形状、结构、材质与文化符号的设计语法。",
        "motif": "筛选有限核心母题并删除次级奇观。",
        "color_light": "锁定大色块层级、物理光源与空气介质。",
        "camera": "把机位、视野和画幅翻译为可观察构图结果。",
    }
    for key, role in CREATIVE_ROLE_SKILLS.items(): nodes.append(graph_node(f"position-{key}", role, objectives[key], shared, "ExpertPositionV1", "parallel"))
    positions = [f"position-{key}" for key in CREATIVE_ROLE_SKILLS]
    nodes.append(graph_node("spec-assembler", "visual-spec-assembler", "合并专家立场，显式记录冲突和可见性覆盖，不用多数投票。", [*shared, *positions], "VisualPromptSpecV1"))
    nodes.extend([graph_node("production-review", "visual-production-critic", "核验构图可读性、材质、身体或空间关系与制作逻辑。", ["spec-assembler"], "AgentResultV1", "parallel"), graph_node("adversarial-review", "adversarial-reviewer", "查找幻觉、俗套、文化误用、过载、第二资产与契约遗漏。", ["spec-assembler"], "AgentResultV1", "parallel"), graph_node("spec-final", "synthesis-adjudicator", "按证据权级裁决冲突，最多一次针对性反驳，形成唯一推荐规格。", ["spec-assembler", "production-review", "adversarial-review", "evidence"], "VisualPromptSpecV1")])
    return {"schema_version": "ExecutionGraphV2", "graph_version": 1, "max_concurrency": 3, "max_replans": 1, "nodes": nodes}


def build_compile_patch(graph: dict[str, Any]) -> dict[str, Any]:
    salience = graph_node("salience-editor", "prompt-salience-editor", "按可见结果与不变量保护价值去重、排序和压缩规格。", ["spec-final"], "PromptSaliencePlanV1")
    compiler = graph_node("openai-compiler", "openai-image-prompt-compiler", "按 OpenAI 官方语义顺序编译一条无标题中文母提示词。", ["salience-editor", "spec-final"], "ImagePromptPackageV2")
    return {"schema_version": "DagPatchV1", "base_graph_version": graph["graph_version"], "operations": [{"op": "add_node", "node": salience}, {"op": "add_node", "node": compiler}], "invalidated_nodes": ["openai-compiler", "salience-editor"], "semantic_impact": "low", "evidence": ["confirmed VisualPromptSpecV1"], "confirmation_required": True}


def flatten_dimensions(requirement: dict[str, Any]) -> list[str]:
    values: list[str] = []
    def visit(value: Any) -> None:
        if isinstance(value, str) and value.strip(): values.append(value.strip())
        elif isinstance(value, dict):
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(requirement.get("design_dimensions", {})); visit(requirement.get("primary_state", {}).get("design_language", [])); visit(requirement.get("primary_state", {}).get("concrete_elements", []))
    return list(dict.fromkeys(values))


def expert_position(role: str, requirement: dict[str, Any], presentation: dict[str, str]) -> dict[str, Any]:
    recommendation = {"visual-brief-director": f"把交付锁定为{presentation['intended_use']}，只服务一个清楚判断。", "visual-hierarchy-director": "建立唯一第一视觉中心，其余信息按剧情和识别优先级退后。", "design-language-director": "让形状、材质、使用历史和文化依据形成同一套可重复语法。", "motif-curator": "只保留三到四个承担叙事或识别功能的核心母题。", "color-light-director": "使用大色块、明确光源动机和有限空气介质，拒绝零碎综合色。", "camera-composition-director": f"用{presentation['framing']}使不变量在{presentation['aspect_ratio']}中可检查。", "character-asset-designer": "完整展示轮廓、比例、姿态、脸发、服装层级与使用痕迹。", "environment-asset-designer": "以空间功能、核心结构、动线、尺度和层级组织纯环境，不用人群填充。", "prop-asset-designer": "完整展示尺度、持握逻辑、机制、材质重量与有因磨损。"}[role]
    refs = sorted({ref for item in requirement.get("evidence", []) for ref in item.get("source_refs", [])})
    return {"schema_version": "ExpertPositionV1", "role": role, "persona_principle": "每个判断必须改变可见结果或保护已确认不变量。", "recommendation": recommendation, "evidence_refs": refs, "priority": "high", "objections": ["无依据新增设计事实", "同等强调所有元素"], "alternative": flatten_dimensions(requirement)[:2], "confidence": "high" if refs else "medium", "change_conditions": "新的封版契约、有效来源或用户明确覆盖该审美判断。"}


def visibility_matrix(requirement: dict[str, Any], presentation: dict[str, str]) -> list[dict[str, Any]]:
    framing, kind = presentation["framing"], requirement["asset"]["asset_type"]
    broad = any(token in framing for token in ("全身", "完整", "超广角", "整体", "全景"))
    if kind in {"location_master", "scene_state"}: broad = broad and not any(token in framing for token in ("人物", "人群", "角色"))
    invariants = list(dict.fromkeys(requirement.get("invariants", [])))
    concrete = list(dict.fromkeys(requirement.get("primary_state", {}).get("concrete_elements", [])))
    return [{"requirement": item, "visible": broad, "invariant": True, "reason": framing} for item in invariants] + [{"requirement": item, "visible": broad, "invariant": False, "reason": framing} for item in concrete]


def build_spec(requirement: dict[str, Any], requirement_hash: str, presentation: dict[str, str], positions: list[dict[str, Any]]) -> dict[str, Any]:
    details, asset = flatten_dimensions(requirement), requirement["asset"]
    facts = [item for item in requirement.get("evidence", []) if item.get("kind") == "fact"]
    constraints = list(dict.fromkeys(requirement.get("exclusions", []) + requirement.get("cultural_boundaries", [])))
    spec = {
        "schema_version": "VisualPromptSpecV1", "version": "v1", "status": "proposed",
        "asset_id": asset["asset_id"], "asset_type": asset["asset_type"], "asset_name": asset["name"],
        "requirement_hash": requirement_hash, "intended_use": presentation["intended_use"],
        "framing": presentation["framing"], "aspect_ratio": presentation["aspect_ratio"],
        "evidence_capsule": [{"statement": item.get("statement", ""), "source_refs": item.get("source_refs", [])} for item in facts],
        "blocks": {
            "brief": f"创建一张{presentation['aspect_ratio']}、用于{presentation['intended_use']}的{asset['name']}单资产图。",
            "hierarchy": requirement.get("design_dimensions", {}).get("shared", {}).get("target_perception", "唯一主体清楚，主次明确"),
            "design_language": requirement.get("primary_state", {}).get("design_language", []) or details[:3],
            "motifs": list(dict.fromkeys(requirement.get("primary_state", {}).get("concrete_elements", [])))[:4],
            "color_light": [item for item in details if any(word in item for word in ("色", "光", "灰", "白", "黑", "蓝", "红", "金", "亮", "暗"))][:6] or ["综合色块清楚，光源动机可信"],
            "camera_composition": [presentation["framing"], presentation["aspect_ratio"]],
            "asset_specific": details,
        },
        "visibility_matrix": visibility_matrix(requirement, presentation), "invariants": requirement.get("invariants", []),
        "exclusions": constraints, "reference_roles": [], "expert_positions": positions,
        "conflicts": [], "resolutions": [], "rebuttal_rounds": 0,
        "spec_confirmation": {"gate": "visual_prompt_spec", "confirmed": False, "confirmed_at": None},
    }
    if asset["asset_type"] in {"location_master", "scene_state"}:
        spec["exclusions"] = list(dict.fromkeys([*spec["exclusions"], "人物或人群"]))
    return spec


def _text_items(value: Any) -> list[str]:
    if isinstance(value, str): return [value.strip()] if value.strip() else []
    if isinstance(value, list): return [item for child in value for item in _text_items(child)]
    if isinstance(value, dict): return [item for child in value.values() for item in _text_items(child)]
    return []


def salience_plan(spec: dict[str, Any]) -> dict[str, Any]:
    ordered: list[str] = []
    for key in ("brief", "hierarchy", "design_language", "motifs", "color_light", "asset_specific", "camera_composition"):
        for item in _text_items(spec["blocks"].get(key)):
            normalized = re.sub(r"\s+", " ", item).strip("；。 ")
            if normalized and normalized not in ordered: ordered.append(normalized)
    return {"schema_version": "PromptSaliencePlanV1", "asset_id": spec["asset_id"], "ordered_visible_clauses": ordered, "constraint_clauses": list(dict.fromkeys(spec.get("exclusions", [])))[:3], "pruning_rule": "每句必须改变可见结果或保护确认过的不变量。"}


def compile_prompt(spec: dict[str, Any], plan: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    plan, blocks = plan or salience_plan(spec), spec["blocks"]
    paragraphs = ["。".join(_text_items(blocks["brief"]) + _text_items(blocks["hierarchy"])), "。".join(_text_items(blocks["asset_specific"])), "。".join(_text_items(blocks["design_language"]) + _text_items(blocks["motifs"])), "。".join(_text_items(blocks["color_light"])), f"{spec['framing']}，画幅为{spec['aspect_ratio']}，构图服务于{spec['intended_use']}。"]
    constraints = plan.get("constraint_clauses", [])[:3]
    if constraints: paragraphs.append("保持" + "；保持".join(constraints) + "。")
    cleaned = []
    for paragraph in paragraphs:
        paragraph = re.sub(r"[。]{2,}", "。", paragraph).strip("。 \n")
        if paragraph: cleaned.append(paragraph + "。")
    return "\n\n".join(cleaned), constraints


def make_prompt(requirement: dict[str, Any], presentation: dict[str, str] | None = None) -> tuple[str, list[str]]:
    presentation = presentation or recommend_presentation(requirement)
    roles = [*CREATIVE_ROLE_SKILLS.values(), ASSET_ROLE_SKILLS[requirement["asset"]["asset_type"]]]
    return compile_prompt(build_spec(requirement, "deterministic-preview", presentation, [expert_position(role, requirement, presentation) for role in roles]))


def base_result(task_id: str, status: str = "succeeded") -> dict[str, Any]:
    return {"schema_version": "AgentResultV1", "task_id": task_id, "status": status, "summary": "completed", "claims": [], "evidence_refs": [], "artifact_refs": [], "conflicts": [], "questions": [], "errors": [], "metrics": {}}


def _claim(dependencies: dict[str, dict[str, Any]], node_id: str, claim_type: str) -> Any:
    for item in dependencies.get(node_id, {}).get("claims", []):
        if item.get("claim_type") == claim_type: return item.get("value")
    return None


class DeterministicExecutor:
    def __init__(self, requirement: dict[str, Any], requirement_hash: str, presentation: dict[str, str], run_id: str) -> None:
        self.requirement, self.requirement_hash, self.presentation, self.run_id = requirement, requirement_hash, presentation, run_id

    def __call__(self, node: dict[str, Any], dependencies: dict[str, dict[str, Any]], attempt: int) -> tuple[dict[str, Any], None]:
        node_id, role = node["node_id"], node["role_skill"]
        result = base_result(f"{self.run_id}:{node_id}:{attempt}")
        if node_id == "evidence":
            facts = [item for item in self.requirement.get("evidence", []) if item.get("kind") == "fact"]
            result["claims"] = [{"claim_type": "evidence_check", "value": {"asset_id": self.requirement["asset"]["asset_id"], "facts": facts, "invariants": self.requirement.get("invariants", [])}}]
            result["evidence_refs"] = sorted({ref for item in facts for ref in item.get("source_refs", [])})
        elif node_id == "reference-role":
            refs = [{"reference_hash": item.get("sha256", hash_json(item)), "allowed_dimension": item.get("responsibility", "single declared dimension"), "forbidden_dimensions": item.get("must_not_control", []), "observations": [], "originality_checks": ["do not copy composition and design identity together"]} for item in self.requirement.get("reference_images", [])]
            result["claims"] = [{"claim_type": "reference_roles", "value": {"schema_version": "ReferenceRoleV1", "asset_id": self.requirement["asset"]["asset_id"], "references": refs}}]
        elif node_id == "asset-specialist" or node_id.startswith("position-"):
            result["claims"] = [{"claim_type": "expert_position", "value": expert_position(role, self.requirement, self.presentation)}]
        elif node_id == "spec-assembler":
            positions = [item["value"] for dep in dependencies.values() for item in dep.get("claims", []) if item.get("claim_type") == "expert_position"]
            result["claims"] = [{"claim_type": "visual_prompt_spec", "value": build_spec(self.requirement, self.requirement_hash, self.presentation, positions)}]
        elif node_id in {"production-review", "adversarial-review"}:
            result["claims"] = [{"claim_type": node_id.replace("-", "_"), "value": "No blocking issue found."}]
        elif node_id == "spec-final":
            spec = deepcopy(_claim(dependencies, "spec-assembler", "visual_prompt_spec"))
            errors = validate_spec(spec or {})
            if errors: raise ValueError("Invalid VisualPromptSpecV1: " + "; ".join(errors))
            result["claims"] = [{"claim_type": "visual_prompt_spec", "value": spec}]
        elif node_id == "salience-editor":
            result["claims"] = [{"claim_type": "prompt_salience_plan", "value": salience_plan(_claim(dependencies, "spec-final", "visual_prompt_spec"))}]
        elif node_id == "openai-compiler":
            spec, plan = deepcopy(_claim(dependencies, "spec-final", "visual_prompt_spec")), _claim(dependencies, "salience-editor", "prompt_salience_plan")
            prompt, constraints = compile_prompt(spec, plan)
            package = {"schema_version": "ImagePromptPackageV2", "version": "v2", "status": "proposed", "asset_id": spec["asset_id"], "asset_type": spec["asset_type"], "asset_name": spec["asset_name"], "requirement_hash": self.requirement_hash, "visual_prompt_spec_hash": spec_content_hash(spec), "generation_prompt": prompt, "adapter_profile": {"id": "openai-gpt-image-primary", "version": "2026-08-v1"}, "trace": {"run_id": self.run_id, "spec_node": "spec-final", "constraint_clauses": constraints, "advanced_details_default": "collapsed"}, "confirmation": None}
            errors = validate_package(package)
            if errors: raise ValueError("Invalid ImagePromptPackageV2: " + "; ".join(errors))
            result["claims"] = [{"claim_type": "image_prompt_package_v2", "value": package}]
        else: raise ValueError(f"Unknown node: {node_id}")
        return result, None


class CodexExecutor:
    def __init__(self, client: AppServerClient, requirement: dict[str, Any], requirement_hash: str, presentation: dict[str, str], context: dict[str, Any], dispatcher_key: str, run_id: str, project: Path, store: EventStore, answers: list[str] | None = None) -> None:
        self.client, self.requirement, self.requirement_hash, self.presentation = client, requirement, requirement_hash, presentation
        self.context, self.dispatcher_key, self.run_id, self.project, self.store = context, dispatcher_key, run_id, project, store
        self.answers, self._active, self._lock = answers or [], {}, threading.Lock()

    def cancel(self, node_id: str) -> None:
        with self._lock: active = self._active.get(node_id)
        if active:
            try: self.client.interrupt_turn(*active)
            except RuntimeError: pass

    def __call__(self, node: dict[str, Any], dependencies: dict[str, dict[str, Any]], attempt: int) -> tuple[dict[str, Any], str | None]:
        task = {"schema_version": "AgentTaskV1", "run_id": self.run_id, "node_id": node["node_id"], "task_id": f"{self.run_id}:{node['node_id']}:{attempt}", "role_skill": node["role_skill"], "objective": node["objective"], "requirement": self.requirement, "presentation": self.presentation, "collaboration_context_projection": self.context, "dependency_results": dependencies, "expected_output_schema": node["output_schema"], "constraints": ["single_asset", "no_user_interview", "no_files", "no_image_generation", "no_design_redesign"], "permissions": node["permissions"], "deadline_seconds": node["hard_timeout_seconds"], "dispatcher_answers": self.answers}
        task["dispatcher_signature"] = sign_task(task, self.dispatcher_key)
        current = next(item for item in self.store.snapshot(self.run_id)["nodes"] if item["node_id"] == node["node_id"])
        def remember_thread(thread_id: str) -> None:
            self.store.set_node_status(self.run_id, node["node_id"], "running", attempts=attempt, thread_id=thread_id, lease_owner="local-scheduler", lease_expires_at=current.get("lease_expires_at"))
        def remember_turn(thread_id: str, turn_id: str) -> None:
            with self._lock: self._active[node["node_id"]] = (thread_id, turn_id)
        result, thread_id = self.client.run_agent(task, node["role_skill"], self.project, AGENT_RESULT_SCHEMA, node["hard_timeout_seconds"], thread_id=current.get("thread_id"), on_thread_started=remember_thread, skill_path=Path(__file__).resolve().parents[2] / node["role_skill"] / "SKILL.md", on_turn_started=remember_turn, sandbox_policy={"type": "readOnly", "access": {"type": "fullAccess"}})
        with self._lock: self._active.pop(node["node_id"], None)
        if result.get("task_id") != task["task_id"]: raise ValueError("AgentResultV1 task_id does not match dispatch")
        if result.get("status") in {"succeeded", "degraded"} or (result.get("status") == "failed" and attempt >= 2):
            try: self.client.archive_thread(thread_id)
            except RuntimeError: pass
        return result, thread_id


def find_spec(snapshot: dict[str, Any]) -> dict[str, Any]:
    node = next((item for item in snapshot["nodes"] if item["node_id"] == "spec-final"), None)
    for claim in (node or {}).get("result", {}).get("claims", []):
        if claim.get("claim_type") == "visual_prompt_spec" and isinstance(claim.get("value"), dict): return deepcopy(claim["value"])
    raise ValueError("run has no VisualPromptSpecV1")


def find_package(snapshot: dict[str, Any]) -> dict[str, Any]:
    node = next((item for item in snapshot["nodes"] if item["node_id"] == "openai-compiler"), None)
    for claim in (node or {}).get("result", {}).get("claims", []):
        if claim.get("claim_type") == "image_prompt_package_v2" and isinstance(claim.get("value"), dict): return deepcopy(claim["value"])
    raise ValueError("run has no ImagePromptPackageV2")


def run_report(snapshot: dict[str, Any], package: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": "RunReportV2", "run_id": snapshot["run_id"], "final_status": snapshot["status"], "graph_version": snapshot["graph_version"], "degraded": bool(snapshot["degraded"]), "replans_used": snapshot["replan_count"], "nodes": [{"node_id": node["node_id"], "status": node["status"], "attempts": node["attempts"], "thread_id": node.get("thread_id"), "errors": node.get("result", {}).get("errors", []) if node.get("result") else []} for node in snapshot["nodes"]], "artifacts": [], "validation": {"package_errors": validate_package(package) if package else []}, "metrics": snapshot.get("metrics", []), "conclusion": "单资产视觉规格已确认并编译为唯一中文母提示词。" if package else "等待视觉规格确认。"}


def next_output_dir(project: Path, requirement: dict[str, Any]) -> Path:
    baseline = requirement.get("baseline_ref", {})
    base = project / "outputs" / "image-prompt-team" / baseline.get("project_id", "project") / baseline.get("draft_id", "draft") / "assets" / requirement["asset"]["asset_id"]
    version = 1
    while (base / f"v{version}").exists(): version += 1
    return base / f"v{version}"


def require_v04(snapshot: dict[str, Any]) -> None:
    if snapshot.get("metadata", {}).get("plugin_version") != PLUGIN_VERSION:
        raise ValueError("pre-v0.4 runs are read/export-only; derive a new v0.4 run")


def materialize(store: EventStore, run_id: str, requirement: dict[str, Any], project: Path) -> dict[str, Any]:
    snapshot = store.snapshot(run_id); require_v04(snapshot)
    if snapshot["status"] not in {"proposed", "degraded_pending_acceptance"}: raise ValueError(f"run status {snapshot['status']} cannot be approved")
    package, spec = find_package(snapshot), find_spec(snapshot)
    package["status"] = "approved"; package["confirmation"] = {"gate": "final_prompt", "confirmed": True, "confirmed_at": utc_now()}
    spec["status"] = "confirmed"; spec["spec_confirmation"] = {"gate": "visual_prompt_spec", "confirmed": True, "confirmed_at": next((item["recorded_at"] for item in snapshot["approvals"] if item["gate"] == "visual_prompt_spec" and item["decision"] == "confirmed"), utc_now())}
    if package["visual_prompt_spec_hash"] != spec_content_hash(spec):
        raise ValueError("ImagePromptPackageV2 does not bind to the confirmed VisualPromptSpecV1 content")
    errors = validate_spec(spec) + validate_package(package)
    if errors: raise ValueError("formal output validation failed: " + "; ".join(errors))
    output = next_output_dir(project.resolve(), requirement); output.mkdir(parents=True, exist_ok=False)
    report = run_report(snapshot, package); report["final_status"] = "approved"
    files = {
        "generation-prompt.txt": package["generation_prompt"].rstrip() + "\n",
        "visual-prompt-spec.json": json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        "prompt-package.json": json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        "decision-log.md": f"# Decision log\n\n- Run: `{run_id}`\n- Requirement hash: `{package['requirement_hash']}`\n- Visual spec hash: `{package['visual_prompt_spec_hash']}`\n- Final confirmation: {package['confirmation']['confirmed_at']}\n- Design statement: linked upstream, not regenerated\n- Negative prompt: not produced\n- Image generation: not performed\n",
        "run-report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    }
    for name, content in files.items():
        path = output / name; path.write_text(content, encoding="utf-8")
        store.append(run_id, "artifact_recorded", {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "kind": name, "node_id": "openai-compiler"})
    store.record_approval(run_id, "final_prompt", "confirmed", {"output": str(output)})
    store.set_run_status(run_id, "approved", degraded=bool(snapshot["degraded"]))
    return {"status": "approved", "run_id": run_id, "output": str(output), "package": package}


def initial_preview(requirement: dict[str, Any], presentation: dict[str, str], accepted: bool = False) -> dict[str, Any]:
    count = 14 + (1 if requirement.get("reference_images") else 0)
    return {"confirmation_required": True, "asset": requirement["asset"], "goal": "编译一条证据约束的 OpenAI 中文母提示词", "presentation": presentation, "presentation_recommendation_accepted": accepted, "expected_agent_turns": f"{count - 2}–{count}", "peak_concurrency": 3, "permissions": ["read sealed requirement", "write local event database", "dispatch read-only Codex Agent turns"], "side_effects": ["consumes Codex usage after confirmation", "no network search", "no image generation", "no external write"]}


def spec_preview(spec: dict[str, Any]) -> dict[str, Any]:
    return {"confirmation_required": True, "asset_id": spec["asset_id"], "intended_use": spec["intended_use"], "framing": spec["framing"], "aspect_ratio": spec["aspect_ratio"], "blocks": spec["blocks"], "visibility_matrix": spec["visibility_matrix"], "conflicts": spec["conflicts"], "resolutions": spec["resolutions"], "exclusions": spec["exclusions"]}


def build_executor(args: argparse.Namespace, client: AppServerClient | None, store: EventStore, snapshot: dict[str, Any], requirement: dict[str, Any], presentation: dict[str, str], project: Path, answers: list[str] | None = None):
    requirement_path = Path(snapshot["metadata"]["requirement_path"])
    if args.backend == "deterministic":
        if not args.test_mode or os.environ.get("ORCHESTRATOR_TEST_MODE") != "1": raise PermissionError("deterministic backend is restricted to explicit test mode")
        return DeterministicExecutor(requirement, file_hash(requirement_path), presentation, snapshot["run_id"]), client
    if client is None: client = AppServerClient(); client.start()
    if not danger_mode_enabled(client.read_config(project)) and args.host_permission_profile != "danger-full-access": raise PermissionError("danger-full-access is required; the plugin will not modify Codex configuration")
    key = os.urandom(32).hex()
    return CodexExecutor(client, requirement, file_hash(requirement_path), presentation, build_context(requirement), key, snapshot["run_id"], project, store, answers), client


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__); root.add_argument("--project", type=Path, default=Path.cwd()); root.add_argument("--db", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preview", "run"):
        command = commands.add_parser(name); command.add_argument("--requirement", type=Path, required=True); command.add_argument("--collaboration-mode", choices=["default", "plan"], default=os.environ.get("CODEX_COLLABORATION_MODE", "default")); command.add_argument("--intended-use"); command.add_argument("--framing"); command.add_argument("--aspect-ratio"); command.add_argument("--accept-presentation-recommendation", action="store_true")
        if name == "run": command.add_argument("--confirm-initial", action="store_true"); command.add_argument("--backend", choices=["app-server", "deterministic"], default="app-server"); command.add_argument("--test-mode", action="store_true"); command.add_argument("--host-permission-profile", choices=["danger-full-access"])
    confirm = commands.add_parser("confirm-spec"); confirm.add_argument("--run-id", required=True); confirm.add_argument("--confirm-spec", action="store_true"); confirm.add_argument("--backend", choices=["app-server", "deterministic"], default="app-server"); confirm.add_argument("--test-mode", action="store_true"); confirm.add_argument("--host-permission-profile", choices=["danger-full-access"])
    approve = commands.add_parser("approve"); approve.add_argument("--run-id", required=True); approve.add_argument("--confirm-final", action="store_true")
    for name in ("status", "cancel"):
        command = commands.add_parser(name); command.add_argument("--run-id", required=True)
    resume = commands.add_parser("resume"); resume.add_argument("--run-id", required=True); resume.add_argument("--backend", choices=["app-server", "deterministic"], default="app-server"); resume.add_argument("--test-mode", action="store_true"); resume.add_argument("--host-permission-profile", choices=["danger-full-access"]); resume.add_argument("--answer", action="append", default=[])
    return root


def main() -> int:
    args = parser().parse_args(); client: AppServerClient | None = None
    try:
        project, db = args.project.resolve(), args.db or default_db(args.project.resolve())
        if args.command in {"preview", "run"}:
            if args.collaboration_mode == "plan": raise PermissionError("Plan Mode cannot create or execute an image-prompt-team run; switch to Default mode")
            requirement_path = args.requirement.resolve(); requirement = read_json(requirement_path); errors = validate_visual_requirement(requirement)
            if errors: raise ValueError("Invalid VisualAssetRequirementV1: " + "; ".join(errors))
            recommended = recommend_presentation(requirement); supplied = {"intended_use": args.intended_use, "framing": args.framing, "aspect_ratio": args.aspect_ratio}; accepted = args.accept_presentation_recommendation or all(supplied.values()); presentation = recommended if args.accept_presentation_recommendation else supplied
            preview = initial_preview(requirement, presentation if accepted else recommended, accepted)
            if args.command == "preview" or not args.confirm_initial or not accepted: print(json.dumps(preview, ensure_ascii=False, indent=2)); return 3
            if any(item["invariant"] and not item["visible"] for item in visibility_matrix(requirement, presentation)): raise ValueError("confirmed framing cannot show every invariant; revise framing upstream of execution")
            contract, graph, store = build_contract(requirement, requirement_path, presentation), build_graph(requirement), EventStore(db)
            key = os.urandom(32).hex(); run_id = store.create_run(contract, graph, {"requirement_path": str(requirement_path), "requirement_hash": file_hash(requirement_path), "plugin_version": PLUGIN_VERSION, "package_version": 2, "presentation": presentation, "dispatcher_key_hash": hashlib.sha256(key.encode()).hexdigest()})
            store.record_approval(run_id, "initial", "confirmed", preview); snapshot = store.snapshot(run_id); executor, client = build_executor(args, client, store, snapshot, requirement, presentation, project)
            snapshot = Scheduler(store, 3).execute(run_id, executor, completion_status="awaiting_spec_confirmation"); spec = find_spec(snapshot)
            payload = {"run_id": run_id, "status": snapshot["status"], "visual_prompt_spec": spec_preview(spec), "advanced": run_report(snapshot)}
        elif args.command == "confirm-spec":
            store = EventStore(db); snapshot = store.snapshot(args.run_id); require_v04(snapshot)
            if snapshot["status"] != "awaiting_spec_confirmation": raise ValueError("run is not awaiting VisualPromptSpec confirmation")
            if not args.confirm_spec: raise PermissionError("VisualPromptSpec confirmation is required")
            requirement_path = Path(snapshot["metadata"]["requirement_path"])
            if file_hash(requirement_path) != snapshot["metadata"]["requirement_hash"]: raise ValueError("requirement changed after run; derive a new v0.4 run")
            requirement, presentation, spec = read_json(requirement_path), snapshot["metadata"]["presentation"], find_spec(snapshot); errors = validate_spec(spec)
            if errors: raise ValueError("Invalid VisualPromptSpecV1: " + "; ".join(errors))
            store.record_approval(args.run_id, "visual_prompt_spec", "confirmed", spec_preview(spec)); store.register_patch(args.run_id, build_compile_patch(store.graph(args.run_id)), confirmed=True)
            current = store.snapshot(args.run_id); executor, client = build_executor(args, client, store, current, requirement, presentation, project); completed = Scheduler(store, 3).execute(args.run_id, executor); package = find_package(completed)
            payload = {"run_id": args.run_id, "status": completed["status"], "generation_prompt": package["generation_prompt"], "advanced": run_report(completed, package)}
        elif args.command == "approve":
            store = EventStore(db)
            if not args.confirm_final: raise PermissionError("final prompt confirmation is required")
            snapshot = store.snapshot(args.run_id); require_v04(snapshot); requirement_path = Path(snapshot["metadata"]["requirement_path"])
            if file_hash(requirement_path) != snapshot["metadata"]["requirement_hash"]: raise ValueError("requirement changed after run; derive a new v0.4 run")
            payload = materialize(store, args.run_id, read_json(requirement_path), project)
        elif args.command == "status": payload = EventStore(db).snapshot(args.run_id)
        elif args.command == "cancel":
            store = EventStore(db); store.cancel(args.run_id); payload = store.snapshot(args.run_id)
        elif args.command == "resume":
            store = EventStore(db); current = store.snapshot(args.run_id); require_v04(current)
            if current["status"] != "awaiting_user": payload = current
            else:
                if not args.answer or len(args.answer) > 3: raise ValueError("resume needs one to three answers")
                store.append(args.run_id, "user_input_recorded", {"answers": args.answer}, actor="user", graph_version=current["graph_version"]); requirement_path = Path(current["metadata"]["requirement_path"])
                if file_hash(requirement_path) != current["metadata"]["requirement_hash"]: raise ValueError("requirement changed after run; derive a new v0.4 run")
                requirement = read_json(requirement_path); executor, client = build_executor(args, client, store, current, requirement, current["metadata"]["presentation"], project, args.answer); phase = "proposed" if any(node["node_id"] == "openai-compiler" for node in store.graph(args.run_id)["nodes"]) else "awaiting_spec_confirmation"; snapshot = Scheduler(store, 3).execute(args.run_id, executor, completion_status=phase); payload = {"run_id": args.run_id, "status": snapshot["status"], "advanced": run_report(snapshot, find_package(snapshot) if phase == "proposed" else None)}
        else: raise ValueError(args.command)
        print(json.dumps(redact(payload), ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, KeyError, PermissionError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False)); return 2
    finally:
        if client: client.close()


if __name__ == "__main__": sys.exit(main())
