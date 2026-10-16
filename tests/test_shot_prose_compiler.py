from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


REPO = Path(__file__).resolve().parents[1]
DIRECTOR_SCRIPT = REPO / "plugins/skill-orchestrator/skills/screenplay-scene-daoyanzu/scripts/scene_director.py"
PROSE_SCRIPT = REPO / "plugins/skill-orchestrator/skills/screenplay-shot-prose-compiler/scripts/shot_prose_compiler.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


director = load_module("shot_prose_director_test", DIRECTOR_SCRIPT)
compiler = load_module("shot_prose_compiler_test", PROSE_SCRIPT)


def base_shot(shot_id: str) -> dict:
    value = {field: "已定" for field in director.SHOT_FIELDS}
    value.update(
        {
            "shot_id": shot_id,
            "scene_id": "scn-001",
            "production_scene_code": "E001S001",
            "beat_ids": ["bea-001"],
            "evidence_refs": ["L1-L2"],
            "duration_seconds": 3,
            "framing": "中景",
            "camera_position": "门外向门内",
            "subject_action": "人物走到门口后站定",
            "performance_target": "脚步由快转慢，抬眼看向屋内",
            "sound": "脚步声",
            "last_state": "人物停在门框内侧",
        }
    )
    return value


def sealed_package() -> dict:
    first = base_shot("E001S001C001")
    second = base_shot("E001S001C002")
    second["shot_segments"] = [
        {
            "segment_id": "E001S001C002-1",
            "beat_ids": ["bea-001"],
            "evidence_refs": ["L1-L2"],
            "framing": "近景",
            "angle": "平视",
            "camera_position": "人物甲肩后拍人物乙",
            "movement": "缓慢推近",
            "subject_action": "人物乙抬眼并开口",
            "performance_target": "先稳住呼吸，再抬眼直视对方",
            "dialogue": "我已经决定了。",
            "sound": "衣料摩擦声",
            "last_state": "人物乙站稳并保持对视",
        },
        {
            "segment_id": "E001S001C002-2",
            "beat_ids": ["bea-001"],
            "evidence_refs": ["L1-L2"],
            "framing": "特写",
            "angle": "平视",
            "camera_position": "人物乙肩后反打人物甲",
            "movement": "固定",
            "subject_action": "人物甲停住动作",
            "performance_target": "呼吸骤停，重心前移但没有迈步",
            "dialogue": "",
            "sound": "短暂停顿",
            "last_state": "人物甲僵在原地",
        },
    ]
    package = {
        "schema_version": "SceneDirectionPackageV1",
        "package_id": "pkg",
        "version": "v1",
        "status": "draft",
        "requirement": {},
        "chief_direction": {},
        "scenes": [
            {
                "scene_id": "scn-001",
                "production_scene_code": "E001S001",
                "title": "告别",
                "shots": [first, second],
            }
        ],
        "decision_log": [],
        "source_trace": [],
        "integrity": {"canonical_json_sha256": None},
    }
    return director.seal_package(package)


def prose_record(source: dict, shot_group_id: str) -> dict:
    record_id = source.get("segment_id") or source.get("shot_id")
    dialogue = source.get("dialogue", "")
    text = (
        f"{source['framing']}，{source['camera_position']}，{source['subject_action']}。"
        f"{source['performance_target']}。{dialogue}衣料和动作带出{source['sound']}。"
        f"镜头结束时，{source['last_state']}。"
    )
    return {
        "record_id": record_id,
        "shot_group_id": shot_group_id,
        "display_id": compiler._display_id(record_id),
        "beat_ids": source["beat_ids"],
        "evidence_refs": source["evidence_refs"],
        "camera_contract": {
            "framing": source["framing"],
            "shooting_relation": source["camera_position"],
            "angle": source.get("angle", "平视"),
            "position": source["camera_position"],
            "movement": source.get("movement", "固定"),
        },
        "visual_action": source["subject_action"],
        "performance": {"emotion_label": "克制", "externalization": source["performance_target"]},
        "dialogue": dialogue,
        "sound_events": [source["sound"]],
        "end_state": source["last_state"],
        "prose": text,
    }


def records(package: dict) -> dict:
    shots = package["scenes"][0]["shots"]
    values = [prose_record(shots[0], shots[0]["shot_id"])]
    values.extend(prose_record(segment, shots[1]["shot_id"]) for segment in shots[1]["shot_segments"])
    return {
        "schema_version": "ShotProseRecordCollectionV1",
        "source_package_sha256": package["integrity"]["canonical_json_sha256"],
        "standard_version": "shot-prose-standard-v1",
        "calibration": {
            "mode": "three_sample",
            "status": "confirmed",
            "sample_record_ids": [item["record_id"] for item in values],
            "confirmed_at": "2026-09-18T00:00:00+08:00",
        },
        "scenes": [
            {
                "scene_id": "scn-001",
                "production_scene_code": "E001S001",
                "title": "告别",
                "baseline": {
                    "director_intent": "亲情告别",
                    "space_axis": "门到床为主轴",
                    "weather_light": "阴天柔光",
                    "ambient_sound": "庭院风声",
                    "initial_state": "人物甲在门外，人物乙在窗侧",
                },
                "records": values,
            }
        ],
    }


class ShotProseCompilerTests(unittest.TestCase):
    def test_accepts_simple_shot_and_contiguous_subshots(self) -> None:
        package = sealed_package()
        self.assertEqual(compiler.validate_records(package, records(package)), [])

    def test_rejects_unsealed_or_tampered_source_package(self) -> None:
        package = sealed_package()
        package["status"] = "draft"
        errors = compiler.validate_records(package, records(package))
        self.assertTrue(any("sealed" in error for error in errors))
        self.assertTrue(any("canonical_json_sha256" in error for error in errors))

    def test_rejects_invalid_subshot_sequence(self) -> None:
        package = sealed_package()
        package["status"] = "draft"
        package["scenes"][0]["shots"][1]["shot_segments"][1]["segment_id"] = "E001S001C002-3"
        package = director.seal_package(package)
        self.assertTrue(any("subshots must start at -1" in error for error in compiler.validate_package(package)))

    def test_rejects_unresolved_camera_alternative_and_dialogue_change(self) -> None:
        package = sealed_package()
        value = records(package)
        value["scenes"][0]["records"][1]["camera_contract"]["angle"] = "平视，也可以平拍"
        value["scenes"][0]["records"][1]["dialogue"] = "我改主意了。"
        errors = compiler.validate_records(package, value)
        self.assertTrue(any("unresolved camera alternative" in error for error in errors))
        self.assertTrue(any("dialogue must exactly match" in error for error in errors))

    def test_rejects_prompt_fields_and_model_language(self) -> None:
        package = sealed_package()
        value = records(package)
        value["prompt"] = "forbidden"
        value["scenes"][0]["records"][0]["prose"] += " 视频提示词。"
        errors = compiler.validate_records(package, value)
        self.assertTrue(any("forbidden prompt/model field" in error for error in errors))
        self.assertTrue(any("prompt, model, audit" in error for error in errors))

    def test_docx_has_one_scene_title_visible_ids_and_no_tables(self) -> None:
        package = sealed_package()
        value = records(package)
        self.assertEqual(compiler.validate_records(package, value), [])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shots.docx"
            compiler.render_docx(package, value, path)
            self.assertTrue(zipfile.is_zipfile(path))
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
                core = archive.read("docProps/core.xml").decode("utf-8")
            self.assertEqual(xml.count("E001 S001"), 1)
            self.assertIn("C001", xml)
            self.assertIn("C002-1", xml)
            self.assertNotIn("E001S001C001", xml)
            self.assertNotIn("<w:tbl", xml)
            self.assertIn(package["integrity"]["canonical_json_sha256"], core)


if __name__ == "__main__":
    unittest.main()
