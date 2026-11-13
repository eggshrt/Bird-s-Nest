#!/usr/bin/env python3
"""Skill Orchestrator 安装后配置脚本

在插件安装后自动执行，创建必要的符号链接让 Codex/Claude Skill 工具能发现插件技能。
"""

from pathlib import Path
import sys


EXPOSED_SKILLS = ['skill-orchestrator', 'chinese-intent-clarifier', 'ai-script-breakdown']
SKILL_DIRS = [
    Path.home() / '.codex' / 'skills',
    Path.home() / '.claude' / 'skills',
]


def setup_skill_links():
    plugin_root = Path(__file__).resolve().parents[1]
    results = []

    for skills_dir in SKILL_DIRS:
        skills_dir.mkdir(parents=True, exist_ok=True)

    for skill_name in EXPOSED_SKILLS:
        source = plugin_root / 'skills' / skill_name
        if not source.exists():
            results.append(f"⚠️  {skill_name}: 源目录不存在 {source}")
            continue
        for skills_dir in SKILL_DIRS:
            target = skills_dir / skill_name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(source)
            results.append(f"✓ {skill_name}: {target} -> {source}")

    return results


if __name__ == '__main__':
    print("Skill Orchestrator 安装后配置...")
    results = setup_skill_links()
    for r in results:
        print(r)
    if any('⚠️' in r for r in results):
        sys.exit(1)
    print("\n✓ 配置完成")
