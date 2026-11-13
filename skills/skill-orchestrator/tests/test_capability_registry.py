"""Tests for the CapabilityRegistryV1 merge, domain listing and search gates.

Run with the orchestrator runtime on PYTHONPATH:
    python3 -m unittest discover -s skills/skill-orchestrator/tests
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import orchestrator_index as oi  # noqa: E402

# Neutral wording: infers no permissions, no side effects, risk "low", confidence 0.45.
NEUTRAL = "storyboard planning helper"
# "publish" in the description infers external:write and risk "high".
RISKY = "publish storyboard to a remote channel"
BASE_CONFIDENCE = 0.45


def write_skill(directory: Path, name: str, description: str = NEUTRAL, body: str = "body") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8")
    return path


def write_plugin(cache: Path, marketplace: str, plugin: str, version: str) -> Path:
    version_dir = cache / marketplace / plugin / version
    (version_dir / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    payload = {"name": plugin, "version": version, "skills": "./skills/"}
    (version_dir / ".codex-plugin" / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    return version_dir


def entry(**changes) -> dict:
    base = {
        "plugin": "demo",
        "domain": "film",
        "inputs": ["scene_brief"],
        "outputs": ["shot_list"],
        "entry_only": False,
        "permissions": [],
        "side_effects": [],
        "risk_level": "low",
        "summary_zh": "示例技能",
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.cache = self.tmp / "cache"
        self.user = self.tmp / "user"
        self.cache.mkdir()
        self.user.mkdir()
        self.registry_path = self.tmp / "capability-registry.json"
        self.output = self.tmp / "catalog.json"
        self.demo = write_plugin(self.cache, "mk", "demo", "1.0.0")

    def plugin_skill(self, name: str, description: str = NEUTRAL, body: str = "body") -> Path:
        return write_skill(self.demo / "skills" / name, name, description, body)

    def user_skill(self, name: str, description: str = NEUTRAL) -> Path:
        return write_skill(self.user / name, name, description)

    def write_registry(self, skills: dict, domains: dict | None = None, schema_version: str = oi.REGISTRY_VERSION) -> None:
        payload = {
            "schema_version": schema_version,
            "domains": {"film": {"title_zh": "影视", "entry_skills": ["alpha"]}, "ops": {"title_zh": "运维", "entry_skills": []}} if domains is None else domains,
            "skills": skills,
        }
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def build(self, **kwargs) -> dict:
        roots = [
            {"path": str(self.user), "scope": "user", "source": "user-codex"},
            {"path": str(self.cache), "scope": "plugin", "source": "plugin-cache"},
        ]
        kwargs.setdefault("registry_path", self.registry_path)
        return oi.build_catalog(self.tmp, self.output, roots=roots, **kwargs)

    def records(self, catalog: dict) -> dict:
        return {item["name"]: item for item in catalog["skills"]}

    def problems(self, catalog: dict) -> list[tuple]:
        return [(item["name"], item["error"]) for item in catalog["registry"]["problems"]]


class RegistryMergeTest(RegistryTestCase):
    def test_registered_skill_gets_types_domain_and_raised_confidence(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(entry_only=True, canonical_entry="alpha-entry")})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], True)
        self.assertIs(record["registry_stale"], False)
        self.assertGreaterEqual(record["confidence"], oi.REGISTERED_CONFIDENCE)
        self.assertIn("scene_brief", record["inputs"])
        self.assertIn("shot_list", record["outputs"])
        self.assertEqual(record["domain"], "film")
        self.assertIs(record["entry_only"], True)
        self.assertEqual(record["canonical_entry"], "alpha-entry")
        self.assertEqual(record["summary_zh"], "示例技能")
        self.assertEqual(catalog["registry"]["applied"], 1)
        self.assertEqual(catalog["stats"]["registered"], 1)
        self.assertEqual(catalog["registry"]["problems"], [])

    def test_canonical_entry_defaults_to_skill_name(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry()})
        record = self.records(self.build())["alpha"]
        self.assertEqual(record["canonical_entry"], "alpha")
        self.assertIs(record["entry_only"], False)

    def test_unregistered_skill_is_not_registered_and_has_no_domain(self) -> None:
        self.plugin_skill("alpha")
        self.plugin_skill("beta")
        self.write_registry({"alpha": entry()})
        record = self.records(self.build())["beta"]
        self.assertIs(record["registered"], False)
        self.assertIs(record["registry_stale"], False)
        self.assertIsNone(record["domain"])
        self.assertIsNone(record["canonical_entry"])
        self.assertIs(record["entry_only"], False)
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)

    def test_missing_registry_file_builds_without_registrations(self) -> None:
        self.plugin_skill("alpha")
        catalog = self.build(registry_path=self.tmp / "absent.json")
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertEqual(catalog["registry"]["applied"], 0)
        self.assertEqual(catalog["registry"]["entries"], 0)
        self.assertEqual(catalog["registry"]["problems"], [])
        self.assertTrue(self.output.is_file())

    def test_use_registry_false_ignores_existing_registry(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry()})
        catalog = self.build(use_registry=False)
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIsNone(record["domain"])
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertIsNone(catalog["registry"]["path"])
        self.assertEqual(catalog["registry"]["entries"], 0)
        self.assertEqual(catalog["registry"]["problems"], [])

    def test_wrong_schema_version_applies_nothing_and_records_problem(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry()}, schema_version="CapabilityRegistryV0")
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertEqual(catalog["registry"]["applied"], 0)
        self.assertEqual(len(catalog["registry"]["problems"]), 1)
        self.assertIn("schema_version", catalog["registry"]["problems"][0]["error"])
        self.assertIn(oi.REGISTRY_VERSION, catalog["registry"]["problems"][0]["error"])

    def test_unparseable_registry_applies_nothing_and_records_problem(self) -> None:
        self.plugin_skill("alpha")
        self.registry_path.write_text("{not json", encoding="utf-8")
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertTrue(catalog["registry"]["problems"][0]["error"].startswith("registry_unreadable"))

    def test_registry_cannot_lower_inferred_risk(self) -> None:
        self.plugin_skill("alpha", RISKY)
        self.write_registry({"alpha": entry(risk_level="low", permissions=[], side_effects=[])})
        inferred = self.records(self.build(use_registry=False))["alpha"]
        self.assertEqual(inferred["risk_level"], "high")
        record = self.records(self.build())["alpha"]
        self.assertIs(record["registered"], True)
        self.assertGreaterEqual(oi.RISK_ORDER[record["risk_level"]], oi.RISK_ORDER[inferred["risk_level"]])
        self.assertEqual(record["risk_level"], "high")
        self.assertIs(record["needs_review"], True)

    def test_registry_cannot_remove_inferred_permissions_or_side_effects(self) -> None:
        self.plugin_skill("alpha", RISKY)
        self.write_registry({"alpha": entry(permissions=["filesystem:read"], side_effects=["writes files"])})
        record = self.records(self.build())["alpha"]
        self.assertEqual(record["permissions"], ["external:write", "filesystem:read"])
        self.assertEqual(record["side_effects"], ["sends or publishes externally", "writes files"])

    def test_registry_can_raise_risk_and_widen_permissions(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(risk_level="high", permissions=["network"])})
        record = self.records(self.build())["alpha"]
        self.assertEqual(record["risk_level"], "high")
        self.assertEqual(record["permissions"], ["network"])
        self.assertIs(record["needs_review"], True)

    def test_invalid_risk_level_is_rejected(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(risk_level="harmless")})
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertEqual(self.problems(catalog), [("alpha", "invalid_risk_level")])

    def test_plugin_entry_does_not_apply_to_user_skill(self) -> None:
        self.user_skill("alpha")
        self.write_registry({"alpha": entry(plugin="demo")})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertNotIn("plugin", record)
        self.assertIs(record["registered"], False)
        self.assertIsNone(record["domain"])
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertEqual(self.problems(catalog), [("alpha", "plugin_mismatch")])

    def test_personal_entry_does_not_apply_to_plugin_skill(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(plugin="personal")})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertEqual(record["plugin"], "demo@mk")
        self.assertIs(record["registered"], False)
        self.assertEqual(self.problems(catalog), [("alpha", "plugin_mismatch")])

    def test_personal_entry_applies_to_user_skill(self) -> None:
        self.user_skill("alpha")
        self.write_registry({"alpha": entry(plugin="personal")})
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], True)
        self.assertEqual(catalog["registry"]["problems"], [])

    def test_entry_for_other_plugin_does_not_apply(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(plugin="other")})
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertEqual(self.problems(catalog), [("alpha", "plugin_mismatch")])

    def test_stale_plugin_version_pin_is_not_applied(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(plugin_version="0.9.0", permissions=["network"])})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertEqual(record["plugin_version"], "1.0.0")
        self.assertIs(record["registered"], False)
        self.assertIs(record["registry_stale"], True)
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertIsNone(record["domain"])
        self.assertEqual(record["inputs"], [])
        self.assertEqual(record["permissions"], [])
        self.assertEqual(self.problems(catalog), [("alpha", "stale_entry")])
        self.assertEqual(catalog["registry"]["applied"], 0)

    def test_stale_content_hash_pin_is_not_applied(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(content_hash="0" * 64)})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIs(record["registry_stale"], True)
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertEqual(self.problems(catalog), [("alpha", "stale_entry")])

    def test_matching_pins_are_applied(self) -> None:
        path = self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(plugin_version="1.0.0", content_hash=oi.sha256_file(path))})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], True)
        self.assertIs(record["registry_stale"], False)
        self.assertEqual(catalog["registry"]["problems"], [])

    def test_unknown_domain_is_rejected(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(domain="nowhere")})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIsNone(record["domain"])
        self.assertEqual(self.problems(catalog), [("alpha", "unknown_domain")])

    def test_empty_inputs_are_rejected_as_missing_types(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(inputs=[])})
        catalog = self.build()
        self.assertIs(self.records(catalog)["alpha"]["registered"], False)
        self.assertEqual(self.problems(catalog), [("alpha", "missing_types")])

    def test_empty_outputs_are_rejected_as_missing_types(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(outputs=None)})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIsNone(record["domain"])
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertEqual(self.problems(catalog), [("alpha", "missing_types")])

    def test_registered_but_absent_skill_is_listed_as_unmatched(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(), "ghost": entry()})
        catalog = self.build()
        self.assertEqual(catalog["registry"]["unmatched"], ["ghost"])
        self.assertEqual(catalog["registry"]["entries"], 2)
        self.assertEqual(catalog["registry"]["applied"], 1)

    def test_rebuild_reflects_edited_registry_entry(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(inputs=["old_in"], outputs=["old_out"], permissions=["network"], risk_level="high", entry_only=True, summary_zh="旧")})
        first = self.records(self.build())["alpha"]
        self.assertEqual((first["inputs"], first["risk_level"]), (["old_in"], "high"))
        self.write_registry({"alpha": entry(domain="ops", inputs=["new_in"], outputs=["new_out"], summary_zh="新")})
        record = self.records(self.build())["alpha"]
        self.assertEqual(record["inputs"], ["new_in"])
        self.assertEqual(record["outputs"], ["new_out"])
        self.assertEqual(record["permissions"], [])
        self.assertEqual(record["risk_level"], "low")
        self.assertIs(record["needs_review"], False)
        self.assertIs(record["entry_only"], False)
        self.assertEqual(record["domain"], "ops")
        self.assertEqual(record["summary_zh"], "新")
        self.assertIs(record["registered"], True)

    def test_rebuild_after_entry_removal_leaves_no_merged_values(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(permissions=["network"], side_effects=["writes files"], risk_level="high", entry_only=True)})
        self.assertIs(self.records(self.build())["alpha"]["registered"], True)
        self.write_registry({})
        catalog = self.build()
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIsNone(record["domain"])
        self.assertIsNone(record["canonical_entry"])
        self.assertIs(record["entry_only"], False)
        self.assertEqual(record["inputs"], [])
        self.assertEqual(record["outputs"], [])
        self.assertEqual(record["permissions"], [])
        self.assertEqual(record["side_effects"], [])
        self.assertEqual(record["risk_level"], "low")
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)
        self.assertNotIn("summary_zh", record)
        self.assertEqual(catalog["stats"]["registered"], 0)

    def test_rebuild_registers_previously_unregistered_unchanged_skill(self) -> None:
        self.plugin_skill("alpha")
        self.assertIs(self.records(self.build(use_registry=False))["alpha"]["registered"], False)
        self.write_registry({"alpha": entry()})
        record = self.records(self.build())["alpha"]
        self.assertIs(record["registered"], True)
        self.assertEqual(record["inputs"], ["scene_brief"])
        self.assertGreaterEqual(record["confidence"], oi.REGISTERED_CONFIDENCE)

    def test_rebuild_without_registry_drops_previous_registration(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(permissions=["network"])})
        self.build()
        record = self.records(self.build(use_registry=False))["alpha"]
        self.assertIs(record["registered"], False)
        self.assertEqual(record["permissions"], [])
        self.assertEqual(record["confidence"], BASE_CONFIDENCE)

    def test_overrides_cannot_forge_registered_flag(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({})
        overrides = self.tmp / "overrides.yaml"
        overrides.write_text("skills:\n  alpha:\n    registered: true\n    registry_stale: true\n    risk_level: medium\n", encoding="utf-8")
        catalog = self.build(overrides_path=overrides)
        record = self.records(catalog)["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIs(record["registry_stale"], False)
        self.assertEqual(record["risk_level"], "medium")  # the override itself was read
        self.assertIs(record["manual_override"], True)
        self.assertEqual(catalog["stats"]["registered"], 0)

    def test_overrides_cannot_clear_registry_stale_flag(self) -> None:
        self.plugin_skill("alpha")
        self.write_registry({"alpha": entry(plugin_version="0.9.0")})
        overrides = self.tmp / "overrides.yaml"
        overrides.write_text("skills:\n  alpha:\n    registered: true\n    registry_stale: false\n", encoding="utf-8")
        record = self.records(self.build(overrides_path=overrides))["alpha"]
        self.assertIs(record["registered"], False)
        self.assertIs(record["registry_stale"], True)


class ListDomainsTest(RegistryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.plugin_skill("film-entry")
        self.plugin_skill("film-role")
        self.plugin_skill("ops-entry")
        self.plugin_skill("loose")
        self.plugin_skill("stale")
        self.write_registry({
            "film-entry": entry(),
            "film-role": entry(entry_only=True, canonical_entry="film-entry"),
            "ops-entry": entry(domain="ops", summary_zh="运维入口"),
            "stale": entry(plugin_version="0.0.1"),
        })
        self.build()

    def names(self, items: list[dict]) -> list[str]:
        return [item["name"] for item in items]

    def test_groups_entry_skills_and_internal_roles_by_domain(self) -> None:
        result = oi.list_domains(self.output)
        self.assertEqual(sorted(result["domains"]), ["film", "ops"])
        film = result["domains"]["film"]
        self.assertEqual(film["title_zh"], "影视")
        self.assertEqual(self.names(film["entry_skills"]), ["film-entry"])
        self.assertEqual(self.names(film["internal_roles"]), ["film-role"])
        ops = result["domains"]["ops"]
        self.assertEqual(self.names(ops["entry_skills"]), ["ops-entry"])
        self.assertEqual(ops["internal_roles"], [])
        self.assertEqual(ops["entry_skills"][0]["summary_zh"], "运维入口")
        self.assertEqual(ops["entry_skills"][0]["plugin"], "demo@mk")
        self.assertEqual(ops["entry_skills"][0]["plugin_version"], "1.0.0")

    def test_unregistered_and_rejected_skills_are_in_no_domain(self) -> None:
        result = oi.list_domains(self.output)
        listed = [name for pack in result["domains"].values() for key in ("entry_skills", "internal_roles") for name in self.names(pack[key])]
        self.assertEqual(sorted(listed), ["film-entry", "film-role", "ops-entry"])
        self.assertEqual(result["stale_or_rejected"], [{"name": "stale", "error": "stale_entry"}])

    def test_domain_argument_filters_to_one_pack(self) -> None:
        result = oi.list_domains(self.output, domain="ops")
        self.assertEqual(list(result["domains"]), ["ops"])
        self.assertEqual(self.names(result["domains"]["ops"]["entry_skills"]), ["ops-entry"])

    def test_unknown_domain_argument_returns_no_packs(self) -> None:
        self.assertEqual(oi.list_domains(self.output, domain="nowhere")["domains"], {})


class SearchGateTest(RegistryTestCase):
    QUERY = "storyboard planning"

    def setUp(self) -> None:
        super().setUp()
        for name in ("film-entry", "film-role", "ops-entry", "loose", "net-tool", "ext-tool", "media-tool", "risky-tool", "medium-tool"):
            self.plugin_skill(name)
        self.write_registry({
            "film-entry": entry(),
            "film-role": entry(entry_only=True, canonical_entry="film-entry"),
            "ops-entry": entry(domain="ops"),
            "net-tool": entry(permissions=["network"]),
            "ext-tool": entry(permissions=["external:write"]),
            "media-tool": entry(permissions=["media:generate"]),
            "risky-tool": entry(risk_level="high"),
            "medium-tool": entry(risk_level="medium"),
        })
        catalog = self.build()
        self.assertEqual(catalog["registry"]["problems"], [])

    def search(self, **kwargs) -> tuple[dict, dict]:
        result = asyncio.run(oi.search_catalog(self.output, self.QUERY, **kwargs))
        self.assertEqual(result["registration_failures"], [])
        candidates = {item["name"]: item for item in result["candidates"]}
        filtered = {item["name"]: item["filter_reasons"] for item in result["filtered"]}
        self.assertEqual(len(candidates) + len(filtered), 9, "every fixture skill should be retrieved")
        return candidates, filtered

    def test_entry_only_records_are_filtered_by_default(self) -> None:
        candidates, filtered = self.search()
        self.assertEqual(filtered, {"film-role": ["entry_only"]})
        self.assertNotIn("film-role", candidates)
        self.assertIn("film-entry", candidates)

    def test_include_entry_only_admits_internal_roles(self) -> None:
        candidates, filtered = self.search(include_entry_only=True)
        self.assertIn("film-role", candidates)
        self.assertIs(candidates["film-role"]["entry_only"], True)
        self.assertEqual(candidates["film-role"]["canonical_entry"], "film-entry")
        self.assertEqual(filtered, {})

    def test_domains_filter_marks_other_domains_as_mismatch(self) -> None:
        candidates, filtered = self.search(domains=["ops"])
        self.assertEqual(sorted(candidates), ["ops-entry"])
        self.assertEqual(candidates["ops-entry"]["domain"], "ops")
        self.assertEqual(filtered["film-entry"], ["domain_mismatch"])
        self.assertEqual(filtered["loose"], ["domain_mismatch"])
        self.assertEqual(filtered["film-role"], ["domain_mismatch", "entry_only"])

    def test_default_min_confidence_keeps_unregistered_skill(self) -> None:
        candidates, filtered = self.search()
        self.assertIn("loose", candidates)
        self.assertIs(candidates["loose"]["registered"], False)
        self.assertEqual(candidates["loose"]["confidence"], BASE_CONFIDENCE)
        self.assertNotIn("loose", filtered)

    def test_min_confidence_filters_unregistered_skill(self) -> None:
        candidates, filtered = self.search(min_confidence=0.8)
        self.assertEqual(filtered["loose"], ["low_confidence"])
        self.assertIn("film-entry", candidates)
        self.assertIs(candidates["film-entry"]["registered"], True)
        self.assertGreaterEqual(candidates["film-entry"]["confidence"], oi.REGISTERED_CONFIDENCE)

    def test_dynamic_expert_denies_network_external_write_and_media_generate(self) -> None:
        self.assertEqual(oi.DYNAMIC_EXPERT_DENIED, {"network", "external:write", "media:generate"})
        candidates, filtered = self.search(dynamic_expert=True)
        for name in ("net-tool", "ext-tool", "media-tool"):
            self.assertEqual(filtered[name], ["denied_permission"], name)
            self.assertNotIn(name, candidates)

    def test_dynamic_expert_filters_unregistered_skill_by_confidence(self) -> None:
        self.assertGreater(oi.DYNAMIC_EXPERT_MIN_CONFIDENCE, BASE_CONFIDENCE)
        self.assertLessEqual(oi.DYNAMIC_EXPERT_MIN_CONFIDENCE, oi.REGISTERED_CONFIDENCE)
        candidates, filtered = self.search(dynamic_expert=True)
        self.assertEqual(filtered["loose"], ["low_confidence"])
        self.assertNotIn("loose", candidates)

    def test_dynamic_expert_filters_risk_above_medium(self) -> None:
        candidates, filtered = self.search(dynamic_expert=True)
        self.assertEqual(filtered["risky-tool"], ["risk>medium"])
        self.assertIn("medium-tool", candidates)
        self.assertEqual(sorted(candidates), ["film-entry", "medium-tool", "ops-entry"])

    def test_without_dynamic_expert_those_skills_are_candidates(self) -> None:
        candidates, _ = self.search()
        for name in ("net-tool", "ext-tool", "media-tool", "risky-tool", "loose"):
            self.assertIn(name, candidates)

    def test_query_without_ascii_terms_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(oi.search_catalog(self.output, "分镜规划"))


if __name__ == "__main__":
    unittest.main()
