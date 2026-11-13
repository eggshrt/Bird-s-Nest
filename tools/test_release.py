"""Tests for tools/release.py. Run: python3 -m unittest discover -s tools"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release  # noqa: E402


class ReleaseToolTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".codex-plugin").mkdir()
        (self.root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "demo", "version": "0.9.0"}), encoding="utf-8")
        for name in ("alpha", "beta"):
            (self.root / "skills" / name).mkdir(parents=True)
            (self.root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        self.assertEqual(self.run_tool("add"), 0)

    def run_tool(self, *argv: str) -> int:
        return release.main(["--root", str(self.root), *argv])

    def lock(self) -> dict:
        return json.loads((self.root / "modules.lock.json").read_text(encoding="utf-8"))

    def version(self) -> str:
        return json.loads((self.root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]

    def edit(self, name: str) -> None:
        (self.root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\nchanged\n", encoding="utf-8")

    def test_add_tracks_every_module_at_1_0_0_and_verify_passes(self) -> None:
        self.assertEqual({k: v["version"] for k, v in self.lock()["modules"].items()}, {"alpha": "1.0.0", "beta": "1.0.0"})
        self.assertEqual(self.run_tool("verify"), 0)

    def test_verify_fails_on_unreleased_change(self) -> None:
        self.edit("alpha")
        self.assertEqual(self.run_tool("verify"), 1)

    def test_bump_releases_only_the_named_module(self) -> None:
        self.edit("alpha")
        self.assertEqual(self.run_tool("bump", "alpha", "--note", "fix wording"), 0)
        modules = self.lock()["modules"]
        self.assertEqual((modules["alpha"]["version"], modules["beta"]["version"]), ("1.0.1", "1.0.0"))
        self.assertEqual(self.version(), "0.9.1")
        self.assertEqual(self.lock()["plugin_version"], "0.9.1")
        self.assertIn("`alpha` 1.0.1: fix wording", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_tool("verify"), 0)

    def test_bump_refuses_unchanged_module(self) -> None:
        self.assertEqual(self.run_tool("bump", "alpha", "--note", "x"), 2)
        self.assertEqual(self.version(), "0.9.0")

    def test_bump_refuses_to_leave_another_changed_module_unreleased(self) -> None:
        self.edit("alpha")
        self.edit("beta")
        self.assertEqual(self.run_tool("bump", "alpha", "--note", "x"), 2)
        self.assertEqual(self.lock()["modules"]["alpha"]["version"], "1.0.0")

    def test_minor_levels(self) -> None:
        self.edit("beta")
        self.assertEqual(self.run_tool("bump", "beta", "--level", "minor", "--plugin-level", "minor", "--note", "new option"), 0)
        self.assertEqual(self.lock()["modules"]["beta"]["version"], "1.1.0")
        self.assertEqual(self.version(), "0.10.0")

    def test_new_module_is_untracked_until_added(self) -> None:
        (self.root / "skills" / "gamma").mkdir()
        (self.root / "skills" / "gamma" / "SKILL.md").write_text("---\nname: gamma\n---\n", encoding="utf-8")
        self.assertEqual(self.run_tool("verify"), 1)
        self.assertEqual(self.run_tool("add", "gamma"), 0)
        self.assertEqual(self.run_tool("verify"), 0)

    def test_plugin_version_edit_without_release_fails_verify(self) -> None:
        (self.root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "demo", "version": "0.9.5"}), encoding="utf-8")
        self.assertEqual(self.run_tool("verify"), 1)

    def test_manifest_lists_every_shipped_file(self) -> None:
        output = self.root.parent / f"{self.root.name}-manifest.json"
        self.addCleanup(lambda: output.unlink(missing_ok=True))
        self.assertEqual(self.run_tool("manifest", "--output", str(output)), 0)
        files = json.loads(output.read_text(encoding="utf-8"))["files"]
        self.assertIn("skills/alpha/SKILL.md", files)
        self.assertIn("modules.lock.json", files)


if __name__ == "__main__":
    unittest.main()
