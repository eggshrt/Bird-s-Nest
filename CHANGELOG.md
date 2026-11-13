# Changelog

## 0.11.0 (2026-11-13)

- `skill-orchestrator` 1.2.0: 知识库强制加载五层防护；post_install 符号链接脚本
- `chinese-intent-clarifier` 1.2.0: 知识库强制加载五层防护；post_install 符号链接脚本

## 0.10.1 (2026-11-13)

- `chinese-intent-clarifier` 1.1.0: 自动触发与前置筛选：判断是否影视需求

## 0.10.0 (2026-11-13)

- `skill-orchestrator` 1.1.0: 三档入口、登记表合并、domains 查询、interfaces 更新、native_bridge 说明

## 0.9.0 (2026-11-13)

- 三档入口（轻量 / 标准 / 正式），按需求轻重分流。
- 中文意图分析模块 `chinese-intent-clarifier`：口语化需求、程度副词、客气表达、行业黑话、复合分解。
- 工作区组织：成果文件中文命名放根部，过程文件收入 `.工程/`；清理工具可释放 16.6% 冗余。
- 三层能力登记表与领域包；动态专家门槛写入检索代码。
- 官方桥接脚本 `native_bridge.py`。
- 模块级发版工具 `tools/release.py` 与 `modules.lock.json`；所有模块从 1.0.0 开始跟踪。
- 可移植性检查 `tools/portability_check.py` 与工作区清理 `tools/workspace_tidy.py`。
- 108 条单元测试全部通过；未做模型驱动的端到端实测。
