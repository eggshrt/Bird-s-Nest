#!/usr/bin/env python3
"""Workspace tidying tool for task directories. Standard library only.

Reports and cleans up process files in task directories. New layout puts all
process files in `.工程/` subdirectories, while legacy runs are directly in
`run_*/` directories.

Commands:
    report --workspace DIR [--json]       analyze without modifying
    prune --workspace DIR [options]       clean up old runs and redundant files

Prune options:
    --redundant          remove redundant files (skill indexes, bridge copies, etc.)
    --keep-runs N        keep only the N most recent completed runs per task
    --yes                actually delete (default is dry-run)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]


class TaskDir(NamedTuple):
    path: Path
    new_process_files: list[Path]
    legacy_runs: list[Path]
    redundant_files: list[Path]


class RunInfo(NamedTuple):
    path: Path
    is_completed: bool
    report_data: dict | None


REDUNDANT_NAMES = {
    "skill-index.json",
    "skill_index.json",
    "native_bridge.py",
    "context.json",
    "__pycache__",
    ".DS_Store",
}

REDUNDANT_PATTERNS = [
    "*.tmp",
]


def get_file_size(path: Path) -> int:
    """Get total size of file or directory."""
    if path.is_file():
        return path.stat().st_size
    elif path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return 0


def format_size(bytes: int) -> str:
    """Format bytes as human-readable size."""
    if bytes < 1024:
        return f"{bytes} B"
    elif bytes < 1024 * 1024:
        return f"{bytes / 1024:.1f} KB"
    else:
        return f"{bytes / (1024 * 1024):.1f} MB"


def is_run_directory(path: Path) -> bool:
    """Check if a directory is a run directory (new or legacy)."""
    if not path.is_dir():
        return False

    # New style: has run.json or run_report.json
    if (path / "run.json").is_file() or (path / "run_report.json").is_file():
        return True

    # Legacy style: has events.sqlite3 or audit.json
    if (path / "events.sqlite3").is_file() or (path / "audit.json").is_file():
        return True

    return False


def find_redundant_in_run(run_dir: Path) -> list[Path]:
    """Find redundant files within a run directory."""
    redundant = []

    # Always redundant
    for name in REDUNDANT_NAMES:
        target = run_dir / name
        if target.exists():
            redundant.append(target)

    # Patterns
    for pattern in REDUNDANT_PATTERNS:
        redundant.extend(run_dir.glob(pattern))

    # audit.json and snapshot.json are redundant only if events.sqlite3 exists
    if (run_dir / "events.sqlite3").is_file():
        for name in ["audit.json", "snapshot.json"]:
            target = run_dir / name
            if target.is_file():
                redundant.append(target)

    # Recursively find __pycache__ and .DS_Store
    for item in run_dir.rglob("__pycache__"):
        if item.is_dir():
            redundant.append(item)
    for item in run_dir.rglob(".DS_Store"):
        if item.is_file():
            redundant.append(item)

    return redundant


def get_run_status(run_dir: Path) -> RunInfo:
    """Determine if a run is completed and extract report data."""
    # Try new-style run_report.json
    report_path = run_dir / "run_report.json"
    if report_path.is_file():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            final_status = data.get("final_status", "")
            is_completed = final_status in ["approved", "canceled", "failed"]
            return RunInfo(run_dir, is_completed, data)
        except (json.JSONDecodeError, OSError):
            pass

    # Try legacy-style report in various locations
    for candidate in [run_dir / "run_report.json", run_dir / "snapshot.json", run_dir / "audit.json"]:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if "final_status" in data:
                    is_completed = data["final_status"] != "running"
                    return RunInfo(run_dir, is_completed, data)
            except (json.JSONDecodeError, OSError):
                pass

    # If we can't determine status, treat as not completed (don't delete)
    return RunInfo(run_dir, False, None)


def scan_task_dir(task_path: Path) -> TaskDir:
    """Scan a single task directory for process files."""
    new_process = []
    legacy_runs = []
    redundant = []

    # New-style: .工程/ subdirectory
    gongcheng = task_path / ".工程"
    if gongcheng.is_dir():
        new_process.append(gongcheng)
        # Find redundant files in new-style runs
        runs_dir = gongcheng / "运行"
        if runs_dir.is_dir():
            for run_dir in runs_dir.iterdir():
                if is_run_directory(run_dir):
                    redundant.extend(find_redundant_in_run(run_dir))

    # Legacy-style: run_* directories
    for item in task_path.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            if is_run_directory(item):
                legacy_runs.append(item)
                redundant.extend(find_redundant_in_run(item))

    return TaskDir(task_path, new_process, legacy_runs, redundant)


def find_all_task_dirs(workspace: Path) -> list[TaskDir]:
    """Recursively find all task directories in workspace."""
    task_dirs = []

    for root, dirs, files in os.walk(workspace):
        root_path = Path(root)

        # Check if this directory has process files
        has_gongcheng = (root_path / ".工程").is_dir()
        has_legacy = any((root_path / d).is_dir() and d.startswith("run_") for d in dirs)

        if has_gongcheng or has_legacy:
            task_dirs.append(scan_task_dir(root_path))

    return task_dirs


def cmd_report(workspace: Path, args: argparse.Namespace) -> tuple[dict, int]:
    """Report workspace usage without modifying anything."""
    task_dirs = find_all_task_dirs(workspace)

    total_new = sum(get_file_size(p) for td in task_dirs for p in td.new_process_files)
    total_legacy = sum(get_file_size(p) for td in task_dirs for p in td.legacy_runs)
    total_redundant = sum(get_file_size(p) for td in task_dirs for p in td.redundant_files)
    total_process_files = sum(
        len(td.new_process_files) + len(td.legacy_runs) + len(td.redundant_files)
        for td in task_dirs
    )

    redundant_list = [
        {"path": str(p.relative_to(workspace)), "size": get_file_size(p)}
        for td in task_dirs for p in td.redundant_files
    ]

    payload = {
        "task_directories": len(task_dirs),
        "total_size_bytes": total_new + total_legacy,
        "new_process_bytes": total_new,
        "legacy_runs_bytes": total_legacy,
        "redundant_bytes": total_redundant,
        "redundant_count": len(redundant_list),
        "redundant_items": sorted(redundant_list, key=lambda x: x["size"], reverse=True)[:20],
    }

    return payload, 0


def is_within_workspace(target: Path, workspace: Path) -> bool:
    """Check if target is within workspace after resolving symlinks."""
    try:
        target_resolved = target.resolve()
        workspace_resolved = workspace.resolve()
        return target_resolved.is_relative_to(workspace_resolved)
    except (OSError, ValueError):
        return False


def delete_safely(path: Path, workspace: Path) -> bool:
    """Delete path only if it's within workspace."""
    if not is_within_workspace(path, workspace):
        return False

    try:
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except OSError:
        return False


def prune_runs_in_task(task_dir: TaskDir, keep_n: int, workspace: Path, dry_run: bool) -> tuple[list[str], int, list[dict]]:
    """Prune old completed runs in a task directory."""
    deleted = []
    freed = 0
    skipped = []

    # Collect all run directories (new and legacy)
    all_runs = []

    # New-style runs
    gongcheng = task_dir.path / ".工程"
    if gongcheng.is_dir():
        runs_dir = gongcheng / "运行"
        if runs_dir.is_dir():
            for run_dir in runs_dir.iterdir():
                if is_run_directory(run_dir):
                    all_runs.append(get_run_status(run_dir))

    # Legacy runs
    for run_dir in task_dir.legacy_runs:
        all_runs.append(get_run_status(run_dir))

    # Separate completed and incomplete
    completed = [r for r in all_runs if r.is_completed]
    incomplete = [r for r in all_runs if not r.is_completed]

    # Sort completed by modification time (newest first)
    completed.sort(key=lambda r: r.path.stat().st_mtime, reverse=True)

    # Keep only the newest N completed runs
    to_delete = completed[keep_n:] if keep_n >= 0 else []

    for run_info in to_delete:
        size = get_file_size(run_info.path)
        rel_path = str(run_info.path.relative_to(workspace))

        if dry_run:
            deleted.append(rel_path)
            freed += size
        else:
            if delete_safely(run_info.path, workspace):
                deleted.append(rel_path)
                freed += size
            else:
                skipped.append({"path": rel_path, "reason": "deletion failed or outside workspace"})

    return deleted, freed, skipped


def cmd_prune(workspace: Path, args: argparse.Namespace) -> tuple[dict, int]:
    """Clean up workspace according to options."""
    task_dirs = find_all_task_dirs(workspace)
    dry_run = not args.yes

    deleted = []
    freed = 0
    skipped = []

    # Delete redundant files
    if args.redundant:
        for td in task_dirs:
            for redundant_file in td.redundant_files:
                # Never delete the .工程/记录.jsonl file
                if redundant_file.name == "记录.jsonl":
                    continue

                size = get_file_size(redundant_file)
                rel_path = str(redundant_file.relative_to(workspace))

                if dry_run:
                    deleted.append(rel_path)
                    freed += size
                else:
                    if delete_safely(redundant_file, workspace):
                        deleted.append(rel_path)
                        freed += size
                    else:
                        skipped.append({"path": rel_path, "reason": "deletion failed or outside workspace"})

    # Prune old runs
    if args.keep_runs is not None:
        for td in task_dirs:
            run_deleted, run_freed, run_skipped = prune_runs_in_task(td, args.keep_runs, workspace, dry_run)
            deleted.extend(run_deleted)
            freed += run_freed
            skipped.extend(run_skipped)

    payload = {
        "dry_run": dry_run,
        "deleted": deleted,
        "freed_bytes": freed,
        "skipped": skipped,
    }

    return payload, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    # Report command
    report = commands.add_parser("report", help="analyze workspace usage")
    report.add_argument("--workspace", type=Path, required=True, help="workspace directory to analyze")
    report.add_argument("--json", action="store_true", help="output JSON instead of human-readable")
    report.set_defaults(handler=cmd_report)

    # Prune command
    prune = commands.add_parser("prune", help="clean up workspace")
    prune.add_argument("--workspace", type=Path, required=True, help="workspace directory to clean")
    prune.add_argument("--redundant", action="store_true", help="delete redundant files")
    prune.add_argument("--keep-runs", type=int, metavar="N", help="keep only N most recent completed runs per task")
    prune.add_argument("--yes", action="store_true", help="actually delete (default is dry-run)")
    prune.set_defaults(handler=cmd_prune)

    args = parser.parse_args(argv)

    try:
        workspace = args.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError(f"workspace not found: {workspace}")

        payload, code = args.handler(workspace, args)

        if args.command == "report" and not args.json:
            print(f"工作区分析：{workspace}")
            print(f"  任务目录数量：{payload['task_directories']}")
            print(f"  总占用：{format_size(payload['total_size_bytes'])}")
            print(f"    新式 .工程/：{format_size(payload['new_process_bytes'])}")
            print(f"    旧式 run_*/：{format_size(payload['legacy_runs_bytes'])}")
            print(f"  可释放冗余项：{payload['redundant_count']} 项，{format_size(payload['redundant_bytes'])}")
            if payload["redundant_items"]:
                print("  最大冗余项（前 20）：")
                for item in payload["redundant_items"][:10]:
                    print(f"    {format_size(item['size'])}: {item['path']}")
        elif args.command == "prune":
            if args.json or True:  # Always output JSON for prune
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                mode = "演练模式" if payload["dry_run"] else "实际删除"
                print(f"{mode}：")
                print(f"  删除项数：{len(payload['deleted'])}")
                print(f"  释放空间：{format_size(payload['freed_bytes'])}")
                if payload["skipped"]:
                    print(f"  跳过：{len(payload['skipped'])} 项")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        return code

    except (OSError, ValueError) as exc:
        payload = {"error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
