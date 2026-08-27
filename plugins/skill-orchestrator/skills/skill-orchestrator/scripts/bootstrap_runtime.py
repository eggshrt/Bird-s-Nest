#!/usr/bin/env python3
"""Opt-in, hash-locked runtime bootstrap for Skill Orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


MIN_VERSION = (3, 12)
IMPORTS = ("agentskills_core", "agentskills_fs", "agentskills_retrieval", "yaml")


def requirement_hash(lock_path: Path) -> str:
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()[:16]


def default_cache_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "cache" / "skill-orchestrator" / "runtime"


def runtime_ready(target: Path) -> bool:
    if not (target / ".installed.json").is_file():
        return False
    sys.path.insert(0, str(target))
    try:
        for module in IMPORTS:
            __import__(module)
    except Exception:
        return False
    finally:
        try:
            sys.path.remove(str(target))
        except ValueError:
            pass
    return True


def report(status: str, lock_path: Path, target: Path, installed: bool) -> dict:
    return {
        "status": status,
        "python": sys.executable,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "requirements_lock": str(lock_path),
        "requirements_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "runtime_path": str(target),
        "installed": installed,
        "network_effect_on_install": "Downloads the four hash-locked Python distributions from the configured pip index.",
        "run_environment": {"PYTHONPATH": str(target)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Perform the opt-in installation.")
    parser.add_argument("--cache-root", type=Path, default=default_cache_root())
    args = parser.parse_args()

    lock_path = Path(__file__).with_name("requirements.lock").resolve()
    if sys.version_info < MIN_VERSION:
        payload = report("unsupported_python", lock_path, args.cache_root, False)
        payload["error"] = "Python 3.12 or newer is required. System Python 3.9 must not be used."
        print(json.dumps(payload, indent=2))
        return 2

    target = args.cache_root.expanduser().resolve() / requirement_hash(lock_path)
    if runtime_ready(target):
        print(json.dumps(report("ready", lock_path, target, True), indent=2))
        return 0

    if not args.install:
        payload = report("confirmation_required", lock_path, target, False)
        payload["install_command"] = f'"{sys.executable}" "{Path(__file__).resolve()}" --install'
        print(json.dumps(payload, indent=2))
        return 3

    target.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--require-hashes",
        "--no-deps",
        "--target",
        str(target),
        "-r",
        str(lock_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        payload = report("install_failed", lock_path, target, False)
        payload["error"] = completed.stderr[-4000:]
        print(json.dumps(payload, indent=2))
        return completed.returncode

    marker = report("ready", lock_path, target, True)
    marker_path = target / ".installed.json"
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    if not runtime_ready(target):
        marker_path.unlink(missing_ok=True)
        payload = report("install_failed", lock_path, target, False)
        payload["error"] = "Packages installed but import verification failed."
        print(json.dumps(payload, indent=2))
        return 4
    print(json.dumps(marker, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
