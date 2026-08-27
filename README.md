# Bird's Nest · Codex Skill Orchestrator

一个面向 Codex 的开源 Skill 编排插件：把口述需求问清楚，检索合适的 Agent Skills，生成依赖明确的执行 DAG，并在确认后执行和验证。v0.2 新增了“完整剧本基线 → 单资产概念设计需求”的垂直工作流。

> Spoken request → aligned contract → Skill retrieval → safe DAG → confirmed execution → evidence-backed result.

## 四个 Skills

### `$grill-me`

严格的需求采访 Skill。它把问题展开为设计树，每轮只追问当前可回答的前沿分支，主动暴露假设、风险和未知项。此文件在 v0.2 中保持字节级不变。

### `$skill-orchestrator`

仅显式调用的总控 Skill。它生成 `RequirementContractV1`，扫描和检索本地 Skills，校验 `ExecutionPlanV1` DAG，在执行确认后串行运行，并输出带验证证据的 `RunReportV1`。失败最多重规划一次；未经明确授权不使用子代理。

### `$ai-script-breakdown`

仅显式调用的全剧本分析 Skill。插件固定了当前完整版本、schema、脚本、测试及逐文件哈希。它建立可追溯的共享、导演、表演执行、美术和 AI 可行性基线，只分析，不生成图像提示词。

### `$screenplay-concept-director`

仅显式调用的单资产视觉开发导演。它要求 Plan Mode，复用 `$grill-me` 与 `$ai-script-breakdown`，从全剧证据中建立四类资产清单：

- `character_master`：人物母版；
- `location_master`：地点母版；
- `scene_state`：具体场景状态；
- `hero_prop`：核心道具。

一次运行只允许一个稳定资产 ID。经过“资产选择、完整设计需求、落盘与验证计划”三道确认门后，输出 `AssetCatalogV1`、`AssetContextSnapshotV1`、`VisualAssetRequirementV1` 和 `CreativePositionV1`。

导演会给出一个明确推荐方向，并把剧本事实、保守推导、创意决定、审美偏好和未知项分开记录。用户拥有最终审美决定权；只有剧本冲突、文化边界、生产不可行或多资产越界能够阻止封版。

## 当前边界

- v0.2 的终点是经确认的单资产概念设计需求。
- 不生成图像提示词、负面词、模型参数、供应商语法或图像。
- 参考图只接受用户提供；除非另行授权，不联网搜索参考图。
- 快照每次从磁盘基线重建，不把聊天记忆当项目事实。
- 未解决的问题不能封版；没有证据的事实写作 `unknown`。
- 发布、付费、破坏性操作、凭据变更及新增外部写入仍需节点级确认。

## 安装

```bash
codex plugin marketplace add eggshrt/Bird-s-Nest
codex plugin add skill-orchestrator@skill-orchestrator-private
```

安装或更新后请新建一个 Codex 任务，使 Skills 被重新发现。

## 使用

```text
$grill-me 帮我彻底检查这个产品想法，在达成共同理解前不要开始实现。
```

```text
$skill-orchestrator 帮我对齐需求、检索 Skills、展示执行 DAG，并在我确认后执行：……
```

```text
$ai-script-breakdown 请为我上传的剧本建立完整、可追溯的多岗位分析基线。
```

```text
$screenplay-concept-director 请基于已完成的剧本基线，和我一起封版“林夏”的人物母版需求。
```

`$screenplay-concept-director` 在非 Plan Mode 会立即停止，不读取剧本，也不创建文件。

## 输出结构

```text
outputs/screenplay-concept-director/<project>/<draft>/
├── asset-catalog.md
├── asset-catalog.json
└── assets/<asset-id>/<version>/
    ├── context-snapshot.json
    ├── requirement.md
    ├── requirement.json
    ├── creative-position.json
    └── decision-log.md
```

`VisualAssetRequirementV1` 是未来下游提示词 Skill 的唯一上游输入；本仓库当前不实现该下游。

## 本地索引与运行时

索引器实现作用域优先级、同名遮蔽、内容哈希增量刷新、增强字段 override、BM25 检索、权限/类型过滤、DAG 校验和外部 Skill 静态审计。单资产脚本只使用 Python 标准库，实现资产清单、名称解析、基线失效检查、确定性上下文快照、跨文件验证和正式落盘。

索引依赖哈希锁定为：

- `agentskills-core==0.5.0`
- `agentskills-fs==0.5.0`
- `agentskills-retrieval==0.5.0`
- `PyYAML==6.0.3`

bootstrap 明确要求 Codex 自带 Python 3.12+，不会回退到系统 Python 3.9。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover \
  -s plugins/skill-orchestrator/skills/ai-script-breakdown/tests -v
```

测试覆盖索引与路由、DAG 和授权、四类资产、同名解析、稳定 ID、主要/衍生状态、哈希失效、上下文确定性、证据、三道门、严格单资产、禁止提示词字段及端到端落盘。路由金标有 34 条，总控目标是 Top-3 ≥ 90%、Top-1 ≥ 80%；概念导演另有至少 20 条 Grill 金标。

## 项目结构

```text
.agents/plugins/marketplace.json
plugins/skill-orchestrator/
├── .codex-plugin/plugin.json
├── locks/ai-script-breakdown.lock.json
└── skills/
    ├── grill-me/
    ├── skill-orchestrator/
    ├── ai-script-breakdown/
    └── screenplay-concept-director/
evals/
├── routing-gold.json
└── concept-grill-gold.json
tests/
├── test_orchestrator.py
└── test_concept_director.py
```

## 方法参考

本实现不依赖第三方运行时。以下项目只作为公开方法参考，并未复制其代码或内容：

- [Agent Skills open standard](https://github.com/agentskills/agentskills)
- [ScriptBreak](https://github.com/wassermanproductions/scriptbreak)
- [image-prompt-architect](https://github.com/zixuanzhou0-ai/image-prompt-architect)
- [cinematic-realism-image-prompt-skill](https://github.com/danniurregp-tech/cinematic-realism-image-prompt-skill)

## License

[MIT](LICENSE)
