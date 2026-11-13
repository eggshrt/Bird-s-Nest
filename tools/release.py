#!/usr/bin/env python3
"""Module-level release tool for this plugin. Standard library only.

Every directory under ``skills/`` is one module with its own version and a
content hash recorded in ``modules.lock.json``. This lets one module be
upgraded and released without touching the others.

    status                      list modules whose content differs from the lock
    bump <module>... --note     release changed modules (module + plugin version)
    verify                      fail if any module or the plugin version drifts
    add <module>                start tracking a new module at 1.0.0
    manifest --output FILE      write a sha256 manifest of every shipped file
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCK = "modules.lock.json"
SCHEMA = "ModuleLockV1"
IGNORED = {"__pycache__", ".DS_Store", ".pytest_cache"}
LEVELS = ("major", "minor", "patch")


def shipped_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*") if p.is_file() and not IGNORED.intersection(p.relative_to(base).parts))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(module_dir: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    files = shipped_files(module_dir)
    for path in files:
        digest.update(path.relative_to(module_dir).as_posix().encode("utf-8") + b"\0" + file_sha(path).encode("ascii") + b"\n")
    return digest.hexdigest(), len(files)


def bump_version(version: str, level: str) -> str:
    parts = [int(part) for part in version.split(".")]
    if len(parts) != 3:
        raise ValueError(f"version must be MAJOR.MINOR.PATCH: {version}")
    index = LEVELS.index(level)
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    return ".".join(map(str, parts))


class Plugin:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest_path = root / ".codex-plugin" / "plugin.json"
        self.lock_path = root / LOCK

    def modules_on_disk(self) -> dict[str, Path]:
        skills = self.root / "skills"
        return {p.name: p for p in sorted(skills.iterdir()) if (p / "SKILL.md").is_file()}

    def manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def lock(self) -> dict:
        if not self.lock_path.is_file():
            return {"schema_version": SCHEMA, "plugin_version": None, "modules": {}}
        return json.loads(self.lock_path.read_text(encoding="utf-8"))

    def write_lock(self, lock: dict) -> None:
        lock["modules"] = dict(sorted(lock["modules"].items()))
        self.lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def drift(self) -> dict[str, list[str]]:
        lock, disk = self.lock(), self.modules_on_disk()
        changed = [name for name, path in disk.items() if name in lock["modules"] and tree_sha(path)[0] != lock["modules"][name]["tree_sha256"]]
        return {
            "changed": changed,
            "untracked": sorted(set(disk) - set(lock["modules"])),
            "missing": sorted(set(lock["modules"]) - set(disk)),
        }


def cmd_status(plugin: Plugin, args: argparse.Namespace) -> tuple[dict, int]:
    lock = plugin.lock()
    return {"plugin_version": plugin.manifest().get("version"), "locked_plugin_version": lock["plugin_version"], **plugin.drift()}, 0


def cmd_verify(plugin: Plugin, args: argparse.Namespace) -> tuple[dict, int]:
    lock, drift = plugin.lock(), plugin.drift()
    problems = [f"{kind}: {name}" for kind, names in drift.items() for name in names]
    if plugin.manifest().get("version") != lock["plugin_version"]:
        problems.append(f"plugin.json version {plugin.manifest().get('version')} != locked {lock['plugin_version']}")
    return {"ok": not problems, "problems": problems, "modules": len(lock["modules"])}, 0 if not problems else 1


def cmd_add(plugin: Plugin, args: argparse.Namespace) -> tuple[dict, int]:
    lock, disk = plugin.lock(), plugin.modules_on_disk()
    added = {}
    for name in args.modules or sorted(set(disk) - set(lock["modules"])):
        if name not in disk:
            raise ValueError(f"no skills/{name}/SKILL.md")
        if name in lock["modules"]:
            raise ValueError(f"already tracked: {name}")
        sha, count = tree_sha(disk[name])
        lock["modules"][name] = {"version": "1.0.0", "tree_sha256": sha, "files": count}
        added[name] = "1.0.0"
    lock["plugin_version"] = lock["plugin_version"] or plugin.manifest().get("version")
    plugin.write_lock(lock)
    return {"added": added}, 0


def cmd_bump(plugin: Plugin, args: argparse.Namespace) -> tuple[dict, int]:
    lock, disk, drift = plugin.lock(), plugin.modules_on_disk(), plugin.drift()
    if drift["untracked"] or drift["missing"]:
        raise ValueError(f"resolve untracked/missing modules first (use `add`, or delete from the lock): {drift}")
    unchanged = [name for name in args.modules if name not in drift["changed"]]
    if unchanged:
        raise ValueError(f"no content change in: {unchanged}")
    left_out = sorted(set(drift["changed"]) - set(args.modules))
    if left_out:
        raise ValueError(f"these modules also changed and must be bumped in the same release: {left_out}")
    released = {}
    for name in args.modules:
        entry = lock["modules"][name]
        entry["version"] = bump_version(entry["version"], args.level)
        entry["tree_sha256"], entry["files"] = tree_sha(disk[name])
        released[name] = entry["version"]
    manifest = plugin.manifest()
    manifest["version"] = bump_version(manifest["version"], args.plugin_level)
    plugin.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lock["plugin_version"] = manifest["version"]
    plugin.write_lock(lock)
    changelog = plugin.root / "CHANGELOG.md"
    previous = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Changelog\n"
    head, _, tail = previous.partition("\n")
    entry_text = f"\n## {manifest['version']} ({date.today().isoformat()})\n\n" + "".join(f"- `{name}` {version}: {args.note}\n" for name, version in released.items())
    changelog.write_text(head + "\n" + entry_text + tail, encoding="utf-8")
    return {"plugin_version": manifest["version"], "released": released}, 0


def cmd_manifest(plugin: Plugin, args: argparse.Namespace) -> tuple[dict, int]:
    files = {path.relative_to(plugin.root).as_posix(): file_sha(path) for path in shipped_files(plugin.root)}
    payload = {"schema_version": "PluginFileManifestV1", "name": plugin.manifest().get("name"), "version": plugin.manifest().get("version"), "files": files}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output": str(args.output), "files": len(files), "version": payload["version"]}, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help="plugin root (defaults to this tool's plugin)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    commands.add_parser("verify").set_defaults(handler=cmd_verify)
    add = commands.add_parser("add")
    add.add_argument("modules", nargs="*")
    add.set_defaults(handler=cmd_add)
    bump = commands.add_parser("bump")
    bump.add_argument("modules", nargs="+")
    bump.add_argument("--level", choices=LEVELS, default="patch", help="module version step")
    bump.add_argument("--plugin-level", choices=LEVELS, default="patch", help="plugin version step")
    bump.add_argument("--note", required=True, help="one-line changelog entry")
    bump.set_defaults(handler=cmd_bump)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.set_defaults(handler=cmd_manifest)
    args = parser.parse_args(argv)
    try:
        payload, code = args.handler(Plugin(args.root.resolve()), args)
    except (OSError, ValueError, KeyError) as exc:
        payload, code = {"error": str(exc)}, 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
