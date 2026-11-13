"""Regression tests for plugin-cache scanning in orchestrator_index.

Run with the orchestrator runtime on PYTHONPATH:
    python3 -m unittest discover -s skills/skill-orchestrator/tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import orchestrator_index as oi  # noqa: E402


def write_skill(directory: Path, name: str, body: str = "body") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: {name} description\n---\n{body}\n", encoding="utf-8")
    return path


def write_plugin(cache: Path, marketplace: str, plugin: str, version: str, manifest: dict | None = None) -> Path:
    version_dir = cache / marketplace / plugin / version
    (version_dir / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    payload = {"name": plugin, "version": version, "skills": "./skills/"} if manifest is None else manifest
    (version_dir / ".codex-plugin" / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    return version_dir


class PluginCacheIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.cache = self.tmp / "cache"
        self.user = self.tmp / "user"
        self.cache.mkdir()
        self.user.mkdir()

    def build(self) -> dict:
        roots = [
            {"path": str(self.user), "scope": "user", "source": "user-codex"},
            {"path": str(self.cache), "scope": "plugin", "source": "plugin-cache"},
        ]
        return oi.build_catalog(self.tmp, self.tmp / "catalog.json", roots=roots)

    def active(self, catalog: dict) -> dict:
        return {item["name"]: item for item in catalog["skills"]}

    def test_highest_version_wins_numerically(self) -> None:
        for version in ("0.9.0", "0.10.0", "0.8.1"):
            write_skill(write_plugin(self.cache, "mk", "demo", version) / "skills" / "alpha", "alpha")
        catalog = self.build()
        record = self.active(catalog)["alpha"]
        self.assertEqual(record["plugin_version"], "0.10.0")
        self.assertEqual(record["plugin"], "demo@mk")
        self.assertIn("/demo/0.10.0/", record["path"])
        self.assertEqual(catalog["plugins"][0]["superseded_versions"], ["0.8.1", "0.9.0"])
        self.assertEqual(catalog["stats"]["shadowed"], 0)

    def test_skill_only_in_old_version_is_not_indexed(self) -> None:
        write_skill(write_plugin(self.cache, "mk", "demo", "0.1.0") / "skills" / "retired", "retired")
        write_skill(write_plugin(self.cache, "mk", "demo", "0.2.0") / "skills" / "current", "current")
        self.assertEqual(sorted(self.active(self.build())), ["current"])

    def test_vendored_plugin_copy_is_ignored(self) -> None:
        host = write_plugin(self.cache, "a-host", "bundle", "0.1.0")
        write_skill(host / "skills" / "own", "own")
        write_skill(host / "bundled-plugins" / "real" / "skills" / "shared", "shared", "stale copy")
        write_skill(write_plugin(self.cache, "z-real", "real", "1.0.0") / "skills" / "shared", "shared")
        catalog = self.build()
        active = self.active(catalog)
        self.assertEqual(sorted(active), ["own", "shared"])
        self.assertEqual(active["shared"]["plugin"], "real@z-real")
        self.assertEqual(catalog["shadowed"], [])

    def test_symlink_alias_is_deduplicated(self) -> None:
        write_skill(write_plugin(self.cache, "mk", "demo", "1.2.3") / "skills" / "alpha", "alpha")
        (self.cache / "mk" / "demo" / "latest").symlink_to(self.cache / "mk" / "demo" / "1.2.3")
        catalog = self.build()
        self.assertEqual(len(catalog["plugins"]), 1)
        self.assertEqual(catalog["plugins"][0]["superseded_versions"], [])
        self.assertEqual(catalog["stats"], {**catalog["stats"], "active": 1, "shadowed": 0})

    def test_user_skill_still_outranks_plugin_skill(self) -> None:
        user_path = write_skill(self.user / "alpha", "alpha")
        write_skill(write_plugin(self.cache, "mk", "demo", "1.0.0") / "skills" / "alpha", "alpha")
        catalog = self.build()
        record = self.active(catalog)["alpha"]
        self.assertEqual(record["path"], str(user_path))
        self.assertNotIn("plugin", record)
        self.assertEqual([item["plugin"] for item in catalog["shadowed"]], ["demo@mk"])

    def test_manifest_skills_path_is_respected(self) -> None:
        custom = write_plugin(self.cache, "mk", "custom", "1.0.0", {"version": "1.0.0", "skills": "./abilities"})
        write_skill(custom / "abilities" / "alpha", "alpha")
        write_skill(custom / "skills" / "beta", "beta")
        none = write_plugin(self.cache, "mk", "noskills", "1.0.0", {"version": "1.0.0"})
        catalog = self.build()
        self.assertEqual(sorted(self.active(catalog)), ["alpha"])
        by_name = {item["plugin"]: item for item in catalog["plugins"]}
        self.assertIsNone(by_name["noskills@mk"]["skills_path"])
        self.assertEqual(by_name["noskills@mk"]["path"], str(none))

    def test_skills_path_outside_plugin_is_rejected(self) -> None:
        write_skill(self.tmp / "outside" / "alpha", "alpha")
        write_plugin(self.cache, "mk", "escape", "1.0.0", {"version": "1.0.0", "skills": "../../../../outside"})
        catalog = self.build()
        self.assertEqual(catalog["skills"], [])
        self.assertIsNone(catalog["plugins"][0]["skills_path"])

    def test_broken_manifest_is_reported_not_fatal(self) -> None:
        broken = write_plugin(self.cache, "mk", "broken", "1.0.0")
        (broken / ".codex-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
        write_skill(broken / "skills" / "lost", "lost")
        write_skill(write_plugin(self.cache, "mk", "fine", "1.0.0") / "skills" / "alpha", "alpha")
        catalog = self.build()
        self.assertEqual(sorted(self.active(catalog)), ["alpha"])
        self.assertEqual(len(catalog["invalid"]), 1)
        self.assertTrue(catalog["invalid"][0]["errors"][0].startswith("plugin_manifest_error"))

    def test_directory_name_is_used_when_manifest_has_no_version(self) -> None:
        write_skill(write_plugin(self.cache, "mk", "demo", "2.0.0", {"skills": "./skills/"}) / "skills" / "alpha", "alpha")
        write_skill(write_plugin(self.cache, "mk", "demo", "10.0.0", {"skills": "./skills/"}) / "skills" / "alpha", "alpha")
        self.assertEqual(self.active(self.build())["alpha"]["plugin_version"], "10.0.0")


class VersionKeyTest(unittest.TestCase):
    def test_orders_versions_seen_in_the_cache(self) -> None:
        ordered = [
            "0.1.0+codex.20260924093911",
            "0.1.13-77c10e110b37",
            "0.1.13",
            "0.8.0",
            "0.8.1",
            "0.14.3",
            "0.14.4",
            "1.0.89",
            "1.0.91",
            "26.1106.51428",
            "26.1111.10934",
        ]
        self.assertEqual(sorted(reversed(ordered), key=oi.version_key), ordered)

    def test_build_metadata_does_not_change_release_order(self) -> None:
        self.assertEqual(oi.version_key("1.2.3+build.9")[:2], oi.version_key("1.2.3")[:2])
        self.assertLess(oi.version_key("1.2.3+build.9"), oi.version_key("1.2.4"))

    def test_non_numeric_version_does_not_raise(self) -> None:
        self.assertLess(oi.version_key("latest"), oi.version_key("0.0.1"))


if __name__ == "__main__":
    unittest.main()
