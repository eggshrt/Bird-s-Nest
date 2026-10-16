from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from concept_fixtures import ConceptFixture
from test_image_prompt_team import SCRIPT, team


class PromptPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        fixture = ConceptFixture(self.base)
        self.requirement_path = fixture.write_package()
        self.requirement = team.load_validated_requirement(self.requirement_path)
        self.db = self.base / "runtime.sqlite3"
        first = self.run_cli(
            "run", "--requirement", str(self.requirement_path), "--confirm-initial",
            "--accept-presentation-recommendation", "--backend", "deterministic", "--test-mode",
        )
        self.run_id = first["run_id"]
        second = self.run_cli(
            "confirm-spec", "--run-id", self.run_id, "--confirm-spec",
            "--backend", "deterministic", "--test-mode",
        )
        self.assertEqual(second["status"], "proposed")
        self.store = team.EventStore(self.db)
        self.events_before = self.store.events(self.run_id)
        self.output = team.next_output_dir(self.base, self.requirement)

    def run_cli(self, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--project", str(self.base), "--db", str(self.db), *args],
            text=True, capture_output=True,
            env={**os.environ, "ORCHESTRATOR_TEST_MODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def assert_clean_failure_then_retry(self) -> None:
        self.assertFalse(self.output.exists(), "failed publication must not consume a version")
        self.assertEqual(list(self.output.parent.iterdir()), [], "staging directory must be removed")
        self.assertEqual(self.store.events(self.run_id), self.events_before)
        self.assertEqual(self.store.snapshot(self.run_id)["status"], "proposed")
        result = team.materialize(self.store, self.run_id, self.requirement, self.base)
        self.assertEqual(Path(result["output"]), self.output)
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"generation-prompt.txt", "visual-prompt-spec.json", "prompt-package.json", "decision-log.md", "run-report.json"},
        )
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])
        artifacts = [event["payload"] for event in self.store.events(self.run_id) if event["kind"] == "artifact_recorded"]
        self.assertEqual(len(artifacts), 5)
        for artifact in artifacts:
            self.assertEqual(artifact["sha256"], team.file_hash(Path(artifact["path"])))
        self.assertEqual(self.store.snapshot(self.run_id)["status"], "approved")

    def test_second_file_write_failure_publishes_nothing_and_retry_succeeds(self) -> None:
        real_write = Path.write_text
        calls = 0

        def fail_second_write(path, content, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second-file write failure")
            return real_write(path, content, *args, **kwargs)

        with patch.object(Path, "write_text", autospec=True, side_effect=fail_second_write):
            with self.assertRaisesRegex(OSError, "second-file write failure"):
                team.materialize(self.store, self.run_id, self.requirement, self.base)
        self.assertEqual(calls, 2)
        self.assert_clean_failure_then_retry()

    def test_rename_failure_publishes_nothing_and_retry_succeeds(self) -> None:
        def fail_rename(staging, target):
            self.assertEqual(len(list(staging.iterdir())), 5, "rename must follow every completed file write")
            self.assertEqual(self.store.events(self.run_id), self.events_before, "artifact events must follow publication")
            self.assertEqual(target, self.output)
            raise OSError("injected publication rename failure")

        with patch.object(Path, "rename", autospec=True, side_effect=fail_rename):
            with self.assertRaisesRegex(OSError, "publication rename failure"):
                team.materialize(self.store, self.run_id, self.requirement, self.base)
        self.assert_clean_failure_then_retry()


if __name__ == "__main__":
    unittest.main()
