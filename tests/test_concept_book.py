from __future__ import annotations

from copy import deepcopy
import json
import unittest

from concept_fixtures import director, valid_position, valid_requirement


def concept_book_fixture() -> tuple[dict, dict]:
    """Complete synthetic display data; these are not runtime approval records."""
    requirement = valid_requirement({
        "asset": {"asset_id": "chr-book", "asset_type": "character_master", "name": "概念书测试角色"},
        "project": {"id": "book-project"}, "draft_id": "draft-book",
        "source_hash": "source-hash-sentinel", "breakdown_hash": "baseline-hash-sentinel",
        "analyzer_hash": "analyzer-hash-sentinel", "context_hash": "context-hash-sentinel",
    })
    requirement.update({
        "contract_revision": 2,
        "output_scope": "single_asset",
        "creative_position_hash": "position-hash-sentinel",
        "integrity": {"requirement_hash": "requirement-hash-sentinel"},
        "dependency_assets": [{
            "ref_asset_id": "loc-reference", "asset_type": "location_master", "version": "v7",
            "requirement_path": "/synthetic/dependency/requirement.json", "requirement_hash": "dependency-hash-sentinel",
        }],
        "reference_images": [{
            "source": "user_provided", "path": "/synthetic/reference.png", "sha256": "reference-hash-sentinel",
            "controls": ["参考图只控制铜的锈色"], "must_not_control": ["参考图不得控制人物身份"],
        }],
        "persistence_plan": {"output_root": "/synthetic/delivery", "files": ["requirement.md", "requirement.json"],
                             "validators": ["schema", "semantic", "disk_freshness"]},
    })
    requirement["design_dimensions"]["shared"]["recognition_anchors"] = {
        "primary": "主锚点测试值", "secondary": [{"name": "次锚点测试名", "notes": ["嵌套笔记甲", "嵌套笔记乙"]}],
    }
    requirement["design_dimensions"]["type_specific"]["bound_props"] = {
        "status": "not_applicable", "reason": "此角色没有随身绑定道具",
    }
    requirement["evidence"] = [
        {"kind": kind, "statement": f"独立证据测试-{kind}", "source_refs": [f"ref-{kind}"]}
        for kind in ["fact", "inference", "design_decision", "preference", "unknown"]
    ]
    requirement["high_impact_decisions"] = [{
        "id": "decision-override", "topic": "袖口纹样", "status": "user_override",
        "original_recommendation": "导演原推荐哨兵", "chosen_option": "用户覆盖选择哨兵",
        "consequence": "覆盖后果哨兵", "approval_evidence": {"message_ref": "decision-user-message-sentinel"},
    }, {
        "id": "decision-accepted", "topic": "布料重量", "status": "accepted",
        "chosen_option": "已采纳方案哨兵", "consequence": "已采纳方案后果哨兵",
    }]
    for index, confirmation in enumerate(requirement["confirmations"]):
        confirmation.update(confirmed_by="user", message_ref=f"gate-user-message-{index}", content_hash=f"gate-hash-{index}")
    position = valid_position("chr-book")
    for key in ["claim", "aesthetic_preference", "alternative", "human_statement"]:
        position[key] = f"创作立场独立字段-{key}"
    for key in ["evidence", "objections", "risks", "change_conditions"]:
        position[key] = [f"创作立场独立列表-{key}-甲", f"创作立场独立列表-{key}-乙"]
    return requirement, position


class ConceptBookTests(unittest.TestCase):
    def test_one_book_retains_full_director_position_decisions_and_user_confirmations(self) -> None:
        requirement, position = concept_book_fixture()
        book = director.render_requirement_markdown(requirement, position)
        for key in ["claim", "aesthetic_preference", "alternative", "human_statement"]:
            self.assertIn(position[key], book)
        for key in ["evidence", "objections", "risks", "change_conditions"]:
            for value in position[key]:
                self.assertIn(value, book)
        for decision in requirement["high_impact_decisions"]:
            for key in ["id", "topic", "chosen_option", "consequence"]:
                self.assertIn(decision[key], book)
        self.assertIn("导演原推荐哨兵", book)
        self.assertIn("decision-user-message-sentinel", book)
        self.assertIn("用户覆盖导演原建议", book)
        self.assertIn("判断置信度：高", book)
        self.assertIn("最终决策权：用户", book)
        for confirmation in requirement["confirmations"]:
            for key in ["confirmed_at", "message_ref", "content_hash"]:
                self.assertIn(confirmation[key], book)
        for label in ["资产选择", "完整设计需求", "落盘与验证计划"]:
            self.assertIn(label, book)

    def test_nested_design_and_execution_boundaries_remain_readable_without_json_dumps(self) -> None:
        requirement, position = concept_book_fixture()
        book = director.render_requirement_markdown(requirement, position)
        self.assertIn("# 《资产概念设计书》", book)
        self.assertIn("资产类型：角色母版", book)
        self.assertIn("通用设计维度", book)
        self.assertIn("**识别锚点**", book)
        for value in ["主锚点测试值", "次锚点测试名", "嵌套笔记甲", "嵌套笔记乙", "此角色没有随身绑定道具"]:
            self.assertIn(value, book)
        self.assertIn("**状态**：不适用", book)
        self.assertNotIn(json.dumps(requirement["design_dimensions"]["shared"]["recognition_anchors"], ensure_ascii=False), book)
        self.assertIn("参考图只控制铜的锈色", book)
        self.assertIn("参考图不得控制人物身份", book)
        self.assertIn("/synthetic/reference.png", book)
        self.assertIn("loc-reference · 场景母版 · v7（只读引用）", book)
        self.assertIn("/synthetic/dependency/requirement.json", book)
        for key in ["production_constraints", "cultural_boundaries", "invariants", "exclusions"]:
            for value in requirement[key]:
                self.assertIn(value, book)
        for state in requirement["derived_states"]:
            for key in ["label", "state_id", "delta_from"]:
                self.assertIn(state[key], book)
            for value in state["changes"] + state["source_refs"]:
                self.assertIn(value, book)
        for criterion in requirement["acceptance_criteria"]:
            for value in criterion.values():
                self.assertIn(value, book)

    def test_evidence_and_all_hashes_are_in_collapsed_audit_appendix(self) -> None:
        requirement, position = concept_book_fixture()
        book = director.render_requirement_markdown(requirement, position)
        main, appendix = book.split("<details>", 1)
        self.assertIn("</details>", appendix)
        for label in ["剧本事实", "推断", "设计决策", "审美偏好", "未知"]:
            self.assertIn(f"**{label}**", appendix)
        for item in requirement["evidence"]:
            self.assertNotIn(item["statement"], main)
            self.assertIn(item["statement"], appendix)
            self.assertIn(item["source_refs"][0], appendix)
        hashes = [value for key, value in requirement["baseline_ref"].items() if key.endswith("_hash")]
        hashes += [requirement["creative_position_hash"], requirement["integrity"]["requirement_hash"],
                   requirement["dependency_assets"][0]["requirement_hash"], requirement["reference_images"][0]["sha256"]]
        hashes += [item["content_hash"] for item in requirement["confirmations"]]
        for digest in hashes:
            self.assertNotIn(digest, main)
            self.assertIn(digest, appendix)
        self.assertIn("VisualAssetRequirementV1", appendix)
        self.assertIn("CreativePositionV1", appendix)
        self.assertIn("/synthetic/delivery", appendix)

    def test_rendering_is_deterministic_non_mutating_and_keeps_literal_details_text_visible(self) -> None:
        requirement, position = concept_book_fixture()
        position["human_statement"] = "选择 <details> 中的形状 & 保留 </details> 标记的字面含义"
        original = deepcopy((requirement, position))
        first = director.render_requirement_markdown(requirement, position)
        self.assertEqual(first, director.render_requirement_markdown(requirement, position))
        self.assertEqual((requirement, position), original)
        self.assertIn("&lt;details&gt;", first)
        self.assertIn("&amp;", first)
        self.assertEqual(first.count("<details>"), 1)
        self.assertEqual(first.count("</details>"), 1)


if __name__ == "__main__":
    unittest.main()
