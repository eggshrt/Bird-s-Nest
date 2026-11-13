# 工作区组织约定

从 0.9.0 起，每个任务目录按以下结构组织：

```
<任务目录>/
├── 成果文件（用户要看的，中文命名，放在根部）
│   ├── 两镜优化建议_v002.txt
│   ├── 镜头2提示词_即梦_v001.txt
│   └── 对齐记录_v003.json
│
└── .工程/（所有过程文件，隐藏目录）
    ├── 记录.jsonl（追加式工作记录）
    └── 运行/（正式运行目录）
        ├── r001_摄影连续性会诊_20261111/
        │   ├── requirement.json
        │   ├── graph.json
        │   ├── events.sqlite3
        │   ├── run_report.json
        │   └── nodes/
        │       ├── camera/
        │       └── continuity/
        └── r002_主控汇总_20261111/
```

## 规则

- **成果文件**：用户直接查看、引用、提交的文件。中文命名，带版本号，描述性强。
- **`.工程/` 目录**：所有过程文件（索引副本、事件库、审计、中间结果）。名字以点开头，多数文件管理器默认隐藏。
- **记录.jsonl**：追加式记录每次操作（时间、档位、技能、输入、输出路径、状态）。持续维护，不按运行分文件。
- **运行目录命名**：`rNNN_<任务描述>_<日期>`，例如 `r001_摄影连续性会诊_20261111`。
- **节点目录路径**：执行图里写相对路径 `nodes/<节点名>`，不再写绝对路径。

## 旧版本迁移

0.8.x 的布局是任务目录下直接有 `run_r001/`、`run_r002/` 等目录，内含 `events.sqlite3`、`audit.json`、`snapshot.json`、`skill-index.json`、`native_bridge.py`、`context.json` 等。迁移办法：

1. 在任务目录下创建 `.工程/运行/`。
2. 把旧的 `run_r001/` 改名为 `r001_<描述>_<日期>/` 并移入 `.工程/运行/`。
3. 删除运行目录里的冗余项：
   - `skill-index.json` / `skill_index.json`（技能索引副本，400-460KB）
   - `native_bridge.py`（手写桥接副本）
   - `context.json`（与 requirement.json 重复）
   - `audit.json` 和 `snapshot.json`（如果同目录有 events.sqlite3，它们可由事件库重新导出）
4. 用户成果文件（如 `两镜优化建议_v002.txt`）留在任务目录根部。

插件自带的 `tools/workspace_tidy.py` 可自动完成这些清理：

```bash
# 报告（只读，不改任何东西）
python3 tools/workspace_tidy.py report --workspace <任务目录>

# 演练（列出将删除的内容，不实际删除）
python3 tools/workspace_tidy.py prune --workspace <任务目录> --redundant --keep-runs 3

# 实际清理（删除冗余项，只保留最新 3 个已结束的运行）
python3 tools/workspace_tidy.py prune --workspace <任务目录> --redundant --keep-runs 3 --yes
```

## 效果

以年会项目导演工作区为例，迁移后可释放约 3.8 MB（16.6% 总量），主要是技能索引副本和可重导出的审计文件。更重要的是：

- 用户打开任务目录，只看到成果文件和对齐记录，不被几十个过程文件干扰。
- `.工程/记录.jsonl` 一个文件维护整个任务历史，方便搜索和回溯，不用在多个 `run_report.json` 间跳转。
- 正式运行的完整审计链仍保留在 `.工程/运行/` 下，需要时可查。
