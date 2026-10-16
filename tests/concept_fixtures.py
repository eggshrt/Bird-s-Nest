"""Synthetic, disk-backed concept contracts shared by integration tests.

Confirmations below are test input, never a mechanism for runtime approvals.
"""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins" / "skill-orchestrator" / "skills" / "screenplay-concept-director" / "scripts" / "concept_director.py"
SPEC = importlib.util.spec_from_file_location("concept_fixture_director", SCRIPT)
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
        "shared": {**{key: f"observable {key}" for key in sorted(director.REQUIRED_SHARED_DIMENSIONS)}, "frame": "全身人物母版" if asset_type == "character_master" else "完整资产全貌"},
        "type_specific": {key: f"observable {key}" for key in sorted(director.REQUIRED_TYPE_DIMENSIONS[asset_type])},
    }


def valid_position(asset_id: str) -> dict:
    return {
        "schema_version": "CreativePositionV1",
        "asset_id": asset_id,
        "claim": "用被反复维护的克制轮廓外显人物控制欲。",
        "evidence": ["L1-L4"],
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


class ConceptFixture:
    """Create a self-contained screenplay baseline and user-confirmed test package."""

    def __init__(self, base: Path, director_module=None, analyzer_root: Path | None = None):
        self.base = Path(base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.director = director_module or director
        self.analyzer_root = analyzer_root or self.director.default_analyzer_root()
        self.source = self.base / "screenplay.fountain"
        self.source.write_text(
            "INT. RIVERSIDE REPAIR SHOP - NIGHT\n"
            "Lin Xia enters the workshop.\n"
            "She sorts the tools before opening the door.\n"
            "The copper key turns in the lock.\n"
            "Rain strikes the roof.\n"
            "She steadies her stance.\n"
            "The key bends during the confrontation.\n"
            "Her right sleeve tears on the door.\n",
            encoding="utf-8",
        )
        self.breakdown_path = self.base / "breakdown.json"
        self.breakdown = sample_breakdown()
        self.breakdown["source_manifest"]["sha256"] = self.director.source_hash(self.source)
        self.breakdown["source_manifest"]["analysis_provenance"] = {
            "analyzer_hash": self.director.hash_tree(self.analyzer_root),
            "source_hash": self.breakdown["source_manifest"]["sha256"],
            "source_path": str(self.source),
            "captured_at": "2026-08-27T00:00:00Z",
        }
        self.output_root = self.base / "outputs"
        self.persist_baseline()
        self.snapshot, self.requirement, self.position = self.make()

    def persist_baseline(self) -> None:
        self.breakdown_path.write_text(json.dumps(self.breakdown, ensure_ascii=False, indent=2), encoding="utf-8")
        self.catalog = self.director.build_catalog(self.breakdown, self.analyzer_root)

    def snapshot_for(self, asset_id: str = "chr-001", **kwargs) -> dict:
        return self.director.build_snapshot(
            self.breakdown, self.catalog, asset_id,
            breakdown_path=self.breakdown_path,
            analyzer_root=self.analyzer_root,
            created_at=kwargs.pop("created_at", "2026-08-27T00:00:00Z"),
            **kwargs,
        )

    def approve(self, requirement: dict, snapshot: dict, position: dict) -> dict:
        """Represent fresh explicit test-user decisions for the supplied exact content."""
        payload = deepcopy(requirement)
        payload.pop("integrity", None)
        payload["creative_position_hash"] = self.director.content_hash(position)
        payload["confirmations"] = []
        for index, gate in enumerate(("asset_selection", "design_requirement", "persistence_plan"), start=1):
            payload["confirmations"].append({
                "gate": gate,
                "confirmed": True,
                "confirmed_by": "user",
                "confirmed_at": f"2026-08-27T01:{index * 5:02d}:00Z",
                "message_ref": f"synthetic-test-user-message-{index}",
                "content_hash": self.director.confirmation_hash(payload, gate),
            })
        return self.director.seal_requirement(payload, snapshot, position, analyzer_root=self.analyzer_root)

    def make(self, asset_id: str = "chr-001", version: str = "v1") -> tuple[dict, dict, dict]:
        snapshot = self.snapshot_for(asset_id)
        position = valid_position(asset_id)
        requirement = valid_requirement(snapshot)
        requirement["version"] = version
        requirement["contract_revision"] = 2
        requirement["dependency_assets"] = []
        requirement["persistence_plan"] = {
            "output_root": str(self.output_root),
            "files": ["context-snapshot.json", "requirement.json", "requirement.md", "creative-position.json", "decision-log.md", "asset-catalog.json"],
            "validators": ["schema", "semantic", "disk_freshness"],
        }
        if snapshot["asset"]["asset_type"] in {"location_master", "scene_state"}:
            requirement["output_scope"] = "pure_environment"
            requirement["primary_state"].update({
                "design_direction": "以空的工作台和门口湿痕呈现场景的使用历史。",
                "design_language": ["纵深由门口到工作台保持清晰", "光源有现实位置"],
                "concrete_elements": ["木工作台上留有维护痕迹", "门口地面连续雨水痕迹"],
            })
            requirement["derived_states"] = []
            requirement["invariants"] = ["门口至工作台的连续空间关系"]
            requirement["exclusions"] = ["人物或人群"]
        if snapshot["asset"]["asset_type"] == "scene_state":
            master_snapshot, master_requirement, master_position = self.make("loc-001")
            master_path = self.base / "dependency" / "loc-001" / "requirement.json"
            self.write_package(master_requirement, master_snapshot, master_position, master_path)
            requirement["dependency_assets"] = [{
                "ref_asset_id": "loc-001", "version": master_requirement["version"],
                "requirement_path": str(master_path),
                "requirement_hash": self.director.requirement_hash(master_requirement),
                "asset_type": "location_master",
            }]
            requirement["design_dimensions"]["type_specific"]["location_master_reference"] = "loc-001"
            requirement["design_dimensions"]["type_specific"]["participants"] = "No visible participants; offscreen narrative context only."
        return snapshot, self.approve(requirement, snapshot, position), position

    def write_package(self, requirement: dict | None = None, snapshot: dict | None = None, position: dict | None = None, path: Path | None = None) -> Path:
        requirement = requirement if requirement is not None else self.requirement
        snapshot = snapshot if snapshot is not None else self.snapshot
        position = position if position is not None else self.position
        path = Path(path or self.base / "requirement.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        for destination, payload in ((path, requirement), (path.parent / "context-snapshot.json", snapshot), (path.parent / "creative-position.json", position), (path.parent / "asset-catalog.json", self.catalog)):
            destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
