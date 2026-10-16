from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/skill-orchestrator/skills/director-knowledge-manager/scripts/knowledge_manager.py"
SPEC = importlib.util.spec_from_file_location("knowledge_manager_test", SCRIPT)
km = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(km)


class KnowledgeManagerTests(unittest.TestCase):
    def test_html_conversion_removes_non_text_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.html"
            path.write_text('<style>bad</style><nav>menu</nav><h1>标题</h1><p>正文</p><script>evil()</script><video>movie</video>', encoding="utf-8")
            value = km.convert(path)
            self.assertIn("标题", value); self.assertIn("正文", value)
            for forbidden in ("bad", "menu", "evil", "movie", "<script"):
                self.assertNotIn(forbidden, value)

    def test_ingest_is_review_pending_and_prompt_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "inbox/提示词导演"; source.mkdir(parents=True)
            (source / "one.html").write_text("<p>text</p>", encoding="utf-8")
            value = km.ingest(root / "inbox", root / "catalog.json", root / "converted")
            self.assertEqual(value["sources"][0]["status"], "review_pending")
            self.assertTrue(value["sources"][0]["isolated"])

    def test_publish_requires_user_review_and_rejects_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "inbox/提示词导演"; source.mkdir(parents=True)
            (source / "one.html").write_text("<p>text</p>", encoding="utf-8")
            value = km.ingest(root / "inbox", root / "catalog.json", root / "converted")
            review = {"schema_version": "DirectorKnowledgeReviewV1", "reviewer": "user", "confirmed_at": "2026-01-01T00:00:00Z", "decisions": {value["sources"][0]["source_id"]: "publish"}}
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "isolated"):
                km.publish(root / "catalog.json", root / "roles.json", root / "review.json")

    def test_user_can_publish_prompt_sources_to_isolated_compiler_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "inbox/提示词导演"; source.mkdir(parents=True)
            (source / "one.html").write_text("<p>text</p>", encoding="utf-8")
            value = km.ingest(root / "inbox", root / "catalog.json", root / "converted")
            source_id = value["sources"][0]["source_id"]
            review = {
                "schema_version": "DirectorKnowledgeReviewV1", "reviewer": "user",
                "confirmed_at": "2026-01-01T00:00:00Z", "publication_scope": "isolated_prompt_only",
                "target_role": "seedance-shot-prompt-compiler", "decisions": {source_id: "publish"},
            }
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            roles = km.publish(root / "catalog.json", root / "roles.json", root / "review.json")
            self.assertEqual([item["role_id"] for item in roles["roles"]], ["seedance-shot-prompt-compiler"])
            self.assertEqual(roles["roles"][0]["source_ids"], [source_id])
            catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["sources"][0]["status"], "published")
            self.assertTrue(catalog["sources"][0]["isolated"])

    def test_performance_and_action_sources_publish_to_director_and_compiler(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ("表演相关", "动作导演"):
                source = root / "inbox" / folder
                source.mkdir(parents=True)
                (source / f"{folder}.md").write_text("# 规则\n正文", encoding="utf-8")
            value = km.ingest(root / "inbox", root / "catalog.json", root / "converted")
            source_ids = [item["source_id"] for item in value["sources"]]
            review = {
                "schema_version": "DirectorKnowledgeReviewV1", "reviewer": "user",
                "confirmed_at": "2026-09-17T00:00:00Z",
                "decisions": {source_id: "publish" for source_id in source_ids},
            }
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            roles = km.publish(root / "catalog.json", root / "roles.json", root / "review.json")
            by_id = {item["role_id"]: item for item in roles["roles"]}
            self.assertEqual(set(by_id["seedance-shot-prompt-compiler"]["source_ids"]), set(source_ids))
            self.assertIn("scene-biaoyan-diaodu-daoyan", by_id)
            self.assertIn("scene-dongzuo-daoyan", by_id)


if __name__ == "__main__":
    unittest.main()
