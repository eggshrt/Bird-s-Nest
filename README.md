# Bird's Nest · Codex Skill Orchestrator

一个面向 Codex 的开源 Skill 编排插件：先把口述需求问清楚，再检索合适的 Agent Skills，生成依赖明确的执行 DAG，经确认后执行并验证结果。

> Spoken request → requirement alignment → Skill retrieval → DAG planning → confirmed execution → evidence-based verification.

## 包含的 Skills

### `$grill-me`

一个严格的需求采访 Skill。它把需求映射成设计树，逐轮询问当前能够回答的“前沿问题”，主动暴露假设、风险、替代路径和需要验证的未知项。只有当所有关键分支都关闭，并且用户确认共同理解后才结束。

适合：产品想法、技术方案、重要决策、复杂交付前的需求澄清与压力测试。

### `$skill-orchestrator`

一个仅允许显式调用的元 Skill。它复用 `$grill-me` 完成需求对齐，然后：

1. 生成 `RequirementContractV1`；
2. 按项目、用户和插件作用域扫描本地 Skills；
3. 使用 BM25 召回、权限/兼容性过滤和正文重排选择候选；
4. 生成并校验 `ExecutionPlanV1` DAG；
5. 展示风险、权限、副作用和验证方法，等待第二次确认；
6. 默认串行执行，逐节点验证，失败时最多重规划一次；
7. 输出带证据的 `RunReportV1`。

普通请求不会隐式触发它。请明确输入 `$skill-orchestrator`。

## 安全边界

- 需求对齐完成前不执行任务。
- 执行计划未获第二次确认前不执行任务。
- 发布、付费、破坏性操作、凭据变更及新增外部写入仍需节点级确认。
- 未明确授权时不使用子代理并行执行。
- GitHub 回退只展示候选，不自动安装或运行外部脚本。
- 外部 Skill 安装前检查路径逃逸、隐藏文件、可执行文件、网络调用与校验和。
- 审计日志默认脱敏，不保存秘密或大段原始正文。

## 安装

```bash
codex plugin marketplace add eggshrt/Bird-s-Nest
codex plugin add skill-orchestrator@skill-orchestrator-private
```

仓库是 marketplace 根目录。安装后请新建一个 Codex 任务，使新 Skills 被重新发现。

## 使用

```text
$grill-me 帮我彻底检查这个产品想法，在达成共同理解前不要开始实现。
```

```text
$skill-orchestrator 帮我对齐这个需求，检索合适的 Skills，展示执行 DAG，并在我确认后执行：……
```

## 本地索引与运行时

确定性索引器位于：

```text
plugins/skill-orchestrator/skills/skill-orchestrator/scripts/orchestrator_index.py
```

它实现 Skill 扫描、同名遮蔽、内容哈希增量刷新、增强字段 override、BM25 检索、DAG/接口校验和外部 Skill 静态审计。

运行时锁定：

- `agentskills-core==0.5.0`
- `agentskills-fs==0.5.0`
- `agentskills-retrieval==0.5.0`
- `PyYAML==6.0.3`

依赖使用哈希锁定，且 bootstrap 明确要求 Codex Python 3.12+；不会回退到系统 Python 3.9。

## 测试

项目包含单元、路由和行为测试，覆盖扫描优先级、YAML 容错、同名遮蔽、哈希失效、override、DAG 环检测、输入输出绑定、权限过滤、子代理授权和单次重规划上限。

当前路由金标包含 34 条任务，验收目标：

- Top-3 召回率 ≥ 90%
- Top-1 命中率 ≥ 80%

```bash
python3 -m unittest discover -s tests -v
```

## 项目结构

```text
.agents/plugins/marketplace.json
plugins/skill-orchestrator/
├── .codex-plugin/plugin.json
└── skills/
    ├── grill-me/
    └── skill-orchestrator/
evals/routing-gold.json
tests/test_orchestrator.py
```

## License

[MIT](LICENSE)
