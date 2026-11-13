#!/usr/bin/env python3
"""Portability checker for plugin distributions. Standard library only.

Scans the plugin for dependencies that only work on the author's machine:
absolute paths, references to skills not bundled in the plugin, broken links,
registry inconsistencies, and content warnings.

    portability_check.py [--root R] [--json]

Exit code: 1 if any errors found, 0 otherwise (warnings don't affect exit).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {"__pycache__", ".DS_Store", ".pytest_cache"}
TEXT_EXTENSIONS = {".md", ".json", ".py", ".yaml", ".yml", ".txt", ".toml"}
SKILL_LINE_THRESHOLD = 200
SKILL_CHAR_THRESHOLD = 16000
DESC_CHAR_THRESHOLD = 500


class Issue(NamedTuple):
    check: str
    path: str
    line: int | None
    detail: str


def is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_EXTENSIONS


def shipped_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*") if p.is_file() and not IGNORED.intersection(p.relative_to(base).parts))


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    """Return frontmatter dict and the line number where body starts."""
    if not lines or not lines[0].strip() == "---":
        return {}, 0
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, 0
    fm = {}
    for line in lines[1:end]:
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, end + 1


def load_allow_list(root: Path) -> dict:
    allow_path = root / "tools" / "portability_allow.json"
    if not allow_path.is_file():
        return {"optional_skills": [], "ignore_paths": []}
    return json.loads(allow_path.read_text(encoding="utf-8"))


def check_absolute_path(root: Path, path: Path, allow_list: dict) -> list[Issue]:
    """Check for machine-specific absolute paths."""
    rel = path.relative_to(root).as_posix()
    if rel in allow_list.get("ignore_paths", []):
        return []
    if path.name.startswith("test_"):
        return []

    lines = read_lines(path)
    issues = []

    # Patterns that indicate absolute paths
    patterns = [
        (r"/Users/[^/\s]+/", "absolute path /Users/<user>/"),
        (r"/home/[^/\s]+/", "absolute path /home/<user>/"),
        (r"C:\\Users\\", "absolute path C:\\Users\\"),
        (r"~/.codex/skills(?!/skill-orchestrator)", "personal skill directory ~/.codex/skills"),
        (r"~/.agents/skills", "personal skill directory ~/.agents/skills"),
    ]

    # Allowed patterns in documentation
    allowed_doc_patterns = [
        r"\$CODEX_HOME",
        r"<project>",
        r"~/.codex/skill-orchestrator/",
    ]

    in_code_block = False
    for line_num, line in enumerate(lines, start=1):
        # Track code blocks in markdown
        if path.suffix == ".md":
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or line.strip().startswith("    "):
                continue

        # Skip Python string literals (lines with quotes containing patterns)
        if path.suffix == ".py":
            # If line has string quotes and the pattern is within quotes, skip
            stripped = line.strip()
            if (stripped.startswith('"') or stripped.startswith("'") or
                stripped.startswith('r"') or stripped.startswith("r'")):
                continue

        for pattern, desc in patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                # Check if this is within an allowed documentation pattern
                is_allowed = any(re.search(ap, line) for ap in allowed_doc_patterns)

                # For Python files, check if inside a string literal
                if path.suffix == ".py" and not is_allowed:
                    # Check if match is within quotes
                    before = line[:match.start()]
                    single_quotes = before.count("'") - before.count("\\'")
                    double_quotes = before.count('"') - before.count('\\"')
                    if single_quotes % 2 == 1 or double_quotes % 2 == 1:
                        # Inside a string literal
                        continue

                if not is_allowed:
                    context = line[max(0, match.start()-20):match.end()+20].strip()
                    issues.append(Issue("absolute_path", rel, line_num, f"{desc} in: {context}"))

    return issues


def check_unknown_skill_reference(root: Path, path: Path, allow_list: dict) -> list[Issue]:
    """Check for $skill-name references to skills not in this plugin."""
    if path.suffix != ".md":
        return []

    rel = path.relative_to(root).as_posix()
    if rel in allow_list.get("ignore_paths", []):
        return []

    # Only check SKILL.md and files in references/
    if path.name != "SKILL.md" and "references" not in path.parts:
        return []

    skills_dir = root / "skills"
    available_skills = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()}
    optional_skills = set(allow_list.get("optional_skills", []))

    lines = read_lines(path)
    issues = []

    # Pattern: $skill-name (lowercase with hyphens, not all-caps env vars)
    pattern = r"\$([a-z][a-z0-9-]+)"

    in_code_block = False
    for line_num, line in enumerate(lines, start=1):
        # Track code blocks
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or line.strip().startswith("    "):
            continue

        matches = re.finditer(pattern, line)
        for match in matches:
            skill_name = match.group(1)
            # Skip if it looks like a shell variable (all lowercase single word after $)
            if skill_name in ["codex", "home", "path", "user", "root"]:
                continue

            if skill_name not in available_skills:
                if skill_name in optional_skills:
                    issues.append(Issue("unknown_skill_reference", rel, line_num, f"optional skill ${skill_name} (warning only)"))
                else:
                    issues.append(Issue("unknown_skill_reference", rel, line_num, f"${skill_name} not found in skills/"))

    return issues


def check_broken_link(root: Path, path: Path, allow_list: dict) -> list[Issue]:
    """Check for broken relative links in markdown."""
    if path.suffix != ".md":
        return []

    rel = path.relative_to(root).as_posix()
    if rel in allow_list.get("ignore_paths", []):
        return []

    lines = read_lines(path)
    issues = []

    # Pattern: [text](path) but not http(s):// or mailto: or #anchor
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"

    for line_num, line in enumerate(lines, start=1):
        matches = re.finditer(pattern, line)
        for match in matches:
            link = match.group(2)
            # Skip external links, anchors, and mailto
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Remove anchor part
            link = link.split("#")[0]
            if not link:
                continue

            # Resolve relative to the markdown file's directory
            target = (path.parent / link).resolve()
            if not target.exists():
                issues.append(Issue("broken_link", rel, line_num, f"link target not found: {link}"))

    return issues


def check_registry_foreign_skill(root: Path, allow_list: dict) -> list[Issue]:
    """Check that capability registry only references bundled skills."""
    registry_path = root / "skills" / "skill-orchestrator" / "references" / "capability-registry.json"
    if not registry_path.is_file():
        return []

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [Issue("registry_foreign_skill", "skills/skill-orchestrator/references/capability-registry.json", None, "failed to parse JSON")]

    plugin_manifest = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(plugin_manifest.read_text(encoding="utf-8"))
        plugin_name = manifest.get("name")
    except (json.JSONDecodeError, OSError):
        plugin_name = None

    skills_dir = root / "skills"
    available_skills = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()}

    issues = []
    skills_dict = registry.get("skills", {})

    for skill_name, skill_info in skills_dict.items():
        if skill_name not in available_skills:
            issues.append(Issue("registry_foreign_skill", "skills/skill-orchestrator/references/capability-registry.json", None, f"skill '{skill_name}' not in skills/"))

        if isinstance(skill_info, dict) and skill_info.get("plugin") != plugin_name:
            issues.append(Issue("registry_foreign_skill", "skills/skill-orchestrator/references/capability-registry.json", None, f"skill '{skill_name}' plugin mismatch: {skill_info.get('plugin')} != {plugin_name}"))

    return issues


def check_skill_too_long(root: Path, path: Path) -> list[Issue]:
    """Warn if SKILL.md body is too long."""
    if path.name != "SKILL.md":
        return []

    lines = read_lines(path)
    _, body_start = parse_frontmatter(lines)
    body_lines = lines[body_start:]
    body_text = "\n".join(body_lines)

    rel = path.relative_to(root).as_posix()
    issues = []

    if len(body_lines) > SKILL_LINE_THRESHOLD:
        issues.append(Issue("skill_too_long", rel, None, f"{len(body_lines)} lines (threshold: {SKILL_LINE_THRESHOLD})"))

    if len(body_text) > SKILL_CHAR_THRESHOLD:
        issues.append(Issue("skill_too_long", rel, None, f"{len(body_text)} characters (threshold: {SKILL_CHAR_THRESHOLD})"))

    return issues


def check_missing_frontmatter(root: Path, path: Path) -> list[Issue]:
    """Check that SKILL.md has proper frontmatter."""
    if path.name != "SKILL.md":
        return []

    lines = read_lines(path)
    fm, _ = parse_frontmatter(lines)

    rel = path.relative_to(root).as_posix()
    issues = []

    if not fm:
        issues.append(Issue("missing_frontmatter", rel, 1, "no frontmatter block found"))
        return issues

    if "name" not in fm:
        issues.append(Issue("missing_frontmatter", rel, 1, "frontmatter missing 'name' field"))

    if "description" not in fm:
        issues.append(Issue("missing_frontmatter", rel, 1, "frontmatter missing 'description' field"))

    # Check name matches directory
    expected_name = path.parent.name
    if fm.get("name") != expected_name:
        issues.append(Issue("missing_frontmatter", rel, 1, f"frontmatter name '{fm.get('name')}' != directory name '{expected_name}'"))

    return issues


def check_description_too_long(root: Path, path: Path) -> list[Issue]:
    """Warn if frontmatter description is too long."""
    if path.name != "SKILL.md":
        return []

    lines = read_lines(path)
    fm, _ = parse_frontmatter(lines)

    description = fm.get("description", "")
    if len(description) > DESC_CHAR_THRESHOLD:
        rel = path.relative_to(root).as_posix()
        return [Issue("description_too_long", rel, 1, f"{len(description)} characters (threshold: {DESC_CHAR_THRESHOLD})")]

    return []


def scan_plugin(root: Path) -> tuple[list[Issue], list[Issue], int, int]:
    """Scan plugin and return (errors, warnings, file_count, module_count)."""
    allow_list = load_allow_list(root)

    errors = []
    warnings = []

    # Check registry first (file-level check)
    registry_issues = check_registry_foreign_skill(root, allow_list)
    errors.extend(registry_issues)

    # Scan all text files
    files = [f for f in shipped_files(root) if is_text_file(f)]

    for path in files:
        # Error-level checks
        errors.extend(check_absolute_path(root, path, allow_list))

        unknown_refs = check_unknown_skill_reference(root, path, allow_list)
        for issue in unknown_refs:
            if "warning only" in issue.detail:
                warnings.append(issue)
            else:
                errors.append(issue)

        errors.extend(check_broken_link(root, path, allow_list))
        errors.extend(check_missing_frontmatter(root, path))

        # Warning-level checks
        warnings.extend(check_skill_too_long(root, path))
        warnings.extend(check_description_too_long(root, path))

    # Count modules
    skills_dir = root / "skills"
    module_count = len([p for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()]) if skills_dir.is_dir() else 0

    return errors, warnings, len(files), module_count


def format_issue(issue: Issue) -> str:
    """Format issue for human-readable output."""
    location = f"{issue.path}:{issue.line}" if issue.line else issue.path
    return f"[{issue.check}] {location} - {issue.detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help="plugin root")
    parser.add_argument("--json", action="store_true", help="output JSON instead of human-readable")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    errors, warnings, file_count, module_count = scan_plugin(root)

    if args.json:
        payload = {
            "ok": len(errors) == 0,
            "errors": [{"check": e.check, "path": e.path, "line": e.line, "detail": e.detail} for e in errors],
            "warnings": [{"check": w.check, "path": w.path, "line": w.line, "detail": w.detail} for w in warnings],
            "scanned_files": file_count,
            "modules": module_count,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if errors:
            print("错误：")
            for e in errors:
                print(f"  {format_issue(e)}")

        if warnings:
            print("警告：")
            for w in warnings:
                print(f"  {format_issue(w)}")

        if not errors and not warnings:
            print("未发现可移植性问题")

        print(f"\n扫描了 {file_count} 个文件，{module_count} 个模块")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
