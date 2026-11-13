"""Tests for tools/portability_check.py. Run: python3 -m unittest discover -s tools"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portability_check  # noqa: E402


class PortabilityCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".codex-plugin").mkdir()
        (self.root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"}), encoding="utf-8"
        )
        (self.root / "skills").mkdir()

    def create_skill(self, name: str, content: str = "", frontmatter: str | None = None) -> Path:
        skill_dir = self.root / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        if frontmatter is None:
            frontmatter = f"---\nname: {name}\ndescription: Test skill\n---\n"
        (skill_dir / "SKILL.md").write_text(frontmatter + content, encoding="utf-8")
        return skill_dir

    def run_check(self, *argv: str) -> int:
        return portability_check.main(["--root", str(self.root), *argv])

    def get_json_output(self) -> dict:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(self.root.parent / "portability_check.py"), "--root", str(self.root), "--json"],
            capture_output=True,
            text=True,
            cwd=self.root.parent,
        )
        # For testing, we'll call the scan function directly
        errors, warnings, file_count, module_count = portability_check.scan_plugin(self.root)
        return {
            "ok": len(errors) == 0,
            "errors": [{"check": e.check, "path": e.path, "line": e.line, "detail": e.detail} for e in errors],
            "warnings": [{"check": w.check, "path": w.path, "line": w.line, "detail": w.detail} for w in warnings],
            "scanned_files": file_count,
            "modules": module_count,
        }

    def test_absolute_path_triggers_error(self) -> None:
        self.create_skill("alpha", content="See /Users/alice/myproject/config.json for details.")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("absolute_path" in e["check"] for e in result["errors"]))

    def test_no_absolute_path_passes(self) -> None:
        self.create_skill("alpha", content="See $CODEX_HOME/config.json for details.")
        result = self.get_json_output()
        errors_about_path = [e for e in result["errors"] if e["check"] == "absolute_path"]
        self.assertEqual(len(errors_about_path), 0)

    def test_allowed_documentation_patterns_not_flagged(self) -> None:
        self.create_skill("alpha", content="Install to $CODEX_HOME or <project>/tools or ~/.codex/skill-orchestrator/registry")
        result = self.get_json_output()
        errors_about_path = [e for e in result["errors"] if e["check"] == "absolute_path"]
        self.assertEqual(len(errors_about_path), 0)

    def test_test_file_literal_exempt(self) -> None:
        test_dir = self.root / "skills" / "alpha"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test_something.py").write_text('assert "/Users/test/" in result', encoding="utf-8")
        result = self.get_json_output()
        errors_about_path = [e for e in result["errors"] if e["check"] == "absolute_path"]
        self.assertEqual(len(errors_about_path), 0)

    def test_unknown_skill_reference_triggers_error(self) -> None:
        self.create_skill("alpha", content="Use $beta for preprocessing.")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("unknown_skill_reference" in e["check"] for e in result["errors"]))

    def test_known_skill_reference_passes(self) -> None:
        self.create_skill("alpha", content="Use $beta first.")
        self.create_skill("beta")
        result = self.get_json_output()
        errors_about_ref = [e for e in result["errors"] if e["check"] == "unknown_skill_reference"]
        self.assertEqual(len(errors_about_ref), 0)

    def test_whitelist_downgrades_to_warning(self) -> None:
        self.create_skill("alpha", content="Use $external-helper if available.")
        (self.root / "tools").mkdir(exist_ok=True)
        (self.root / "tools" / "portability_allow.json").write_text(
            json.dumps({"optional_skills": ["external-helper"]}), encoding="utf-8"
        )
        result = self.get_json_output()
        self.assertTrue(result["ok"])  # No errors
        self.assertTrue(any("unknown_skill_reference" in w["check"] for w in result["warnings"]))

    def test_broken_link_triggers_error(self) -> None:
        self.create_skill("alpha", content="See [details](./missing.md) for more.")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("broken_link" in e["check"] for e in result["errors"]))

    def test_valid_link_passes(self) -> None:
        skill_dir = self.create_skill("alpha", content="See [ref](./refs.md) for more.")
        (skill_dir / "refs.md").write_text("# References", encoding="utf-8")
        result = self.get_json_output()
        errors_about_link = [e for e in result["errors"] if e["check"] == "broken_link"]
        self.assertEqual(len(errors_about_link), 0)

    def test_external_link_not_checked(self) -> None:
        self.create_skill("alpha", content="See [docs](https://example.com) or [email](mailto:test@example.com).")
        result = self.get_json_output()
        errors_about_link = [e for e in result["errors"] if e["check"] == "broken_link"]
        self.assertEqual(len(errors_about_link), 0)

    def test_missing_frontmatter_triggers_error(self) -> None:
        self.create_skill("alpha", content="No frontmatter here.", frontmatter="")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing_frontmatter" in e["check"] for e in result["errors"]))

    def test_missing_name_in_frontmatter_triggers_error(self) -> None:
        self.create_skill("alpha", frontmatter="---\ndescription: Test\n---\n")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        errors = [e for e in result["errors"] if e["check"] == "missing_frontmatter" and "name" in e["detail"]]
        self.assertGreater(len(errors), 0)

    def test_name_mismatch_triggers_error(self) -> None:
        self.create_skill("alpha", frontmatter="---\nname: beta\ndescription: Test\n---\n")
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        errors = [e for e in result["errors"] if e["check"] == "missing_frontmatter" and "directory" in e["detail"]]
        self.assertGreater(len(errors), 0)

    def test_valid_frontmatter_passes(self) -> None:
        self.create_skill("alpha")
        result = self.get_json_output()
        errors_about_fm = [e for e in result["errors"] if e["check"] == "missing_frontmatter"]
        self.assertEqual(len(errors_about_fm), 0)

    def test_skill_too_long_triggers_warning(self) -> None:
        long_content = "\n".join([f"Line {i}" for i in range(250)])
        self.create_skill("alpha", content=long_content)
        result = self.get_json_output()
        self.assertTrue(result["ok"])  # Warning, not error
        self.assertTrue(any("skill_too_long" in w["check"] for w in result["warnings"]))

    def test_description_too_long_triggers_warning(self) -> None:
        long_desc = "x" * 600
        self.create_skill("alpha", frontmatter=f"---\nname: alpha\ndescription: {long_desc}\n---\n")
        result = self.get_json_output()
        self.assertTrue(result["ok"])  # Warning, not error
        self.assertTrue(any("description_too_long" in w["check"] for w in result["warnings"]))

    def test_registry_foreign_skill_triggers_error(self) -> None:
        self.create_skill("skill-orchestrator")
        registry_dir = self.root / "skills" / "skill-orchestrator" / "references"
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "capability-registry.json").write_text(
            json.dumps({"skills": {"missing-skill": {"plugin": "test-plugin"}}}), encoding="utf-8"
        )
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("registry_foreign_skill" in e["check"] for e in result["errors"]))

    def test_registry_plugin_mismatch_triggers_error(self) -> None:
        self.create_skill("skill-orchestrator")
        self.create_skill("alpha")
        registry_dir = self.root / "skills" / "skill-orchestrator" / "references"
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "capability-registry.json").write_text(
            json.dumps({"skills": {"alpha": {"plugin": "wrong-plugin"}}}), encoding="utf-8"
        )
        result = self.get_json_output()
        self.assertFalse(result["ok"])
        self.assertTrue(any("registry_foreign_skill" in e["check"] and "mismatch" in e["detail"] for e in result["errors"]))

    def test_return_code_reflects_errors(self) -> None:
        self.create_skill("alpha", content="Bad path /Users/alice/file")
        self.assertEqual(self.run_check(), 1)

        # Fix the error
        self.create_skill("alpha", content="Good content")
        self.assertEqual(self.run_check(), 0)

    def test_warnings_dont_affect_return_code(self) -> None:
        long_content = "\n".join([f"Line {i}" for i in range(250)])
        self.create_skill("alpha", content=long_content)
        self.assertEqual(self.run_check(), 0)


if __name__ == "__main__":
    unittest.main()
