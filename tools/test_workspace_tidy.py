"""Tests for tools/workspace_tidy.py. Run: python3 -m unittest discover -s tools"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workspace_tidy  # noqa: E402


class WorkspaceTidyTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)

    def create_task_dir(self, name: str) -> Path:
        task_dir = self.workspace / name
        task_dir.mkdir(parents=True, exist_ok=True)
        # Add a deliverable file to mark it as a task dir
        (task_dir / "requirement.json").write_text("{}", encoding="utf-8")
        return task_dir

    def create_new_run(self, task_dir: Path, run_name: str, status: str = "approved") -> Path:
        gongcheng = task_dir / ".工程"
        gongcheng.mkdir(exist_ok=True)
        runs_dir = gongcheng / "运行"
        runs_dir.mkdir(exist_ok=True)
        run_dir = runs_dir / run_name
        run_dir.mkdir(exist_ok=True)
        (run_dir / "run_report.json").write_text(
            json.dumps({"final_status": status}), encoding="utf-8"
        )
        return run_dir

    def create_legacy_run(self, task_dir: Path, run_name: str, status: str = "approved") -> Path:
        run_dir = task_dir / run_name
        run_dir.mkdir(exist_ok=True)
        (run_dir / "events.sqlite3").write_text("fake db", encoding="utf-8")
        if status:
            (run_dir / "snapshot.json").write_text(
                json.dumps({"final_status": status}), encoding="utf-8"
            )
        return run_dir

    def add_redundant_files(self, run_dir: Path, with_events: bool = False) -> None:
        (run_dir / "skill-index.json").write_text("{}", encoding="utf-8")
        (run_dir / "native_bridge.py").write_text("# bridge", encoding="utf-8")
        (run_dir / "context.json").write_text("{}", encoding="utf-8")
        (run_dir / ".DS_Store").write_text("", encoding="utf-8")
        (run_dir / "test.tmp").write_text("", encoding="utf-8")

        if with_events:
            (run_dir / "events.sqlite3").write_text("fake db", encoding="utf-8")
            (run_dir / "audit.json").write_text("{}", encoding="utf-8")
            (run_dir / "snapshot.json").write_text("{}", encoding="utf-8")

    def run_report(self) -> dict:
        payload, _ = workspace_tidy.cmd_report(
            self.workspace,
            type('Args', (), {'json': True})()
        )
        return payload

    def run_prune(self, redundant: bool = False, keep_runs: int | None = None, yes: bool = False) -> dict:
        payload, _ = workspace_tidy.cmd_prune(
            self.workspace,
            type('Args', (), {'redundant': redundant, 'keep_runs': keep_runs, 'yes': yes})()
        )
        return payload

    def test_report_counts_correctly(self) -> None:
        task1 = self.create_task_dir("task1")
        self.create_new_run(task1, "run1")
        self.create_legacy_run(task1, "run_001")

        task2 = self.create_task_dir("task2")
        self.create_new_run(task2, "run2")

        result = self.run_report()
        self.assertEqual(result["task_directories"], 2)
        self.assertGreater(result["total_size_bytes"], 0)

    def test_report_identifies_redundant_files(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        self.add_redundant_files(run, with_events=True)

        result = self.run_report()
        self.assertGreater(result["redundant_count"], 0)
        self.assertGreater(result["redundant_bytes"], 0)

    def test_dry_run_does_not_delete(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        self.add_redundant_files(run)

        result = self.run_prune(redundant=True, yes=False)
        self.assertTrue(result["dry_run"])
        self.assertGreater(len(result["deleted"]), 0)

        # Files should still exist
        self.assertTrue((run / "skill-index.json").exists())

    def test_yes_flag_actually_deletes(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        self.add_redundant_files(run)

        result = self.run_prune(redundant=True, yes=True)
        self.assertFalse(result["dry_run"])
        self.assertGreater(len(result["deleted"]), 0)

        # Files should be gone
        self.assertFalse((run / "skill-index.json").exists())
        self.assertFalse((run / "native_bridge.py").exists())

    def test_redundant_rule_without_events_db(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        (run / "audit.json").write_text("{}", encoding="utf-8")

        # Without events.sqlite3, audit.json is NOT redundant
        result = self.run_report()
        redundant_paths = [item["path"] for item in result["redundant_items"]]
        self.assertNotIn("task/.工程/运行/run1/audit.json", redundant_paths)

    def test_redundant_rule_with_events_db(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        (run / "events.sqlite3").write_text("fake", encoding="utf-8")
        (run / "audit.json").write_text("{}", encoding="utf-8")

        # With events.sqlite3, audit.json IS redundant
        self.add_redundant_files(run, with_events=True)
        result = self.run_prune(redundant=True, yes=True)

        self.assertFalse((run / "audit.json").exists())

    def test_keep_runs_preserves_newest(self) -> None:
        task = self.create_task_dir("task")
        run1 = self.create_legacy_run(task, "run_001", status="approved")
        run2 = self.create_legacy_run(task, "run_002", status="approved")
        run3 = self.create_legacy_run(task, "run_003", status="approved")

        # Make run2 newest, run1 oldest
        import time
        time.sleep(0.01)
        run3.touch()
        time.sleep(0.01)
        run2.touch()

        result = self.run_prune(keep_runs=2, yes=True)

        # Should delete only the oldest completed run
        self.assertFalse(run1.exists())
        self.assertTrue(run2.exists())
        self.assertTrue(run3.exists())

    def test_keep_runs_preserves_incomplete(self) -> None:
        task = self.create_task_dir("task")
        run1 = self.create_legacy_run(task, "run_001", status="approved")
        run2 = self.create_legacy_run(task, "run_002", status="running")
        run3 = self.create_legacy_run(task, "run_003", status="")  # No status = incomplete

        result = self.run_prune(keep_runs=0, yes=True)

        # Should delete only completed runs
        self.assertFalse(run1.exists())
        self.assertTrue(run2.exists())
        self.assertTrue(run3.exists())

    def test_never_deletes_task_root_files(self) -> None:
        task = self.create_task_dir("task")
        deliverable = task / "output.txt"
        deliverable.write_text("important", encoding="utf-8")

        run = self.create_legacy_run(task, "run_001", status="approved")

        result = self.run_prune(keep_runs=0, yes=True)

        # Run should be deleted, but deliverable preserved
        self.assertFalse(run.exists())
        self.assertTrue(deliverable.exists())

    def test_never_deletes_jilu_jsonl(self) -> None:
        task = self.create_task_dir("task")
        gongcheng = task / ".工程"
        gongcheng.mkdir()
        jilu = gongcheng / "记录.jsonl"
        jilu.write_text('{"event": "test"}\n', encoding="utf-8")

        result = self.run_prune(redundant=True, yes=True)

        # 记录.jsonl should never be deleted
        self.assertTrue(jilu.exists())

    def test_workspace_boundary_check(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")

        # Create a symlink pointing outside workspace
        external = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: external.rmdir())
        external_file = external / "external.txt"
        external_file.write_text("outside", encoding="utf-8")
        self.addCleanup(external_file.unlink)

        link = run / "external_link"
        try:
            link.symlink_to(external_file)
        except OSError:
            self.skipTest("Symlinks not supported on this platform")

        # Try to delete - should be skipped
        result = self.run_prune(redundant=True, yes=True)

        # External file should not be deleted
        self.assertTrue(external_file.exists())

    def test_multiple_tasks_handled_correctly(self) -> None:
        task1 = self.create_task_dir("project1/task1")
        self.create_legacy_run(task1, "run_001", status="approved")
        self.create_legacy_run(task1, "run_002", status="approved")

        task2 = self.create_task_dir("project2/task2")
        self.create_legacy_run(task2, "run_001", status="approved")

        result = self.run_prune(keep_runs=1, yes=True)

        # Should keep 1 per task, delete 1 from task1
        self.assertEqual(len(result["deleted"]), 1)
        self.assertIn("project1/task1/run_001", result["deleted"][0])

    def test_size_calculation_includes_subdirectories(self) -> None:
        task = self.create_task_dir("task")
        run = self.create_new_run(task, "run1")
        nodes = run / "nodes"
        nodes.mkdir()
        (nodes / "node1").mkdir()
        (nodes / "node1" / "output.txt").write_text("x" * 1000, encoding="utf-8")

        result = self.run_report()
        self.assertGreater(result["total_size_bytes"], 1000)


if __name__ == "__main__":
    unittest.main()
