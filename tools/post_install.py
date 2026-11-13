#!/usr/bin/env python3
"""Skill Orchestrator 安装后配置脚本

在插件安装后自动执行，创建必要的符号链接让 Codex Skill 工具能发现插件技能。
"""

from pathlib import Path
import sys

def setup_skill_links():
    """创建符号链接到 ~/.codex/skills/"""
    plugin_root = Path(__file__).resolve().parents[1]
    codex_skills = Path.home() / '.codex' / 'skills'

    # 确保目标目录存在
    codex_skills.mkdir(parents=True, exist_ok=True)

    # 需要暴露的技能
    exposed_skills = ['skill-orchestrator', 'chinese-intent-clarifier']

    results = []
    for skill_name in exposed_skills:
        source = plugin_root / 'skills' / skill_name
        target = codex_skills / skill_name

        if not source.exists():
            results.append(f"⚠️  {skill_name}: 源目录不存在 {source}")
            continue

        # 删除已存在的链接或文件
        if target.is_symlink() or target.exists():
            target.unlink()

        # 创建符号链接
        target.symlink_to(source)
        results.append(f"✓ {skill_name}: {target} -> {source}")

    return results

if __name__ == '__main__':
    print("Skill Orchestrator 安装后配置...")
    results = setup_skill_links()
    for r in results:
        print(r)

    # 如果有任何失败，返回非零退出码
    if any('⚠️' in r for r in results):
        sys.exit(1)

    print("\n✓ 配置完成")
