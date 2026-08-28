# Bird's Nest · Skill Orchestrator

**让图像提示词成为可审查的视觉设计结果，而不是一串失控的形容词。**

Bird's Nest 是一个面向 Codex 的开源创意编排插件。它把口述需求逐步对齐为剧本证据、单资产概念契约和结构化视觉规格，再让一组独立专家通过可恢复 DAG 协作，最终只交付一条可直接使用的 OpenAI 中文母提示词。

```text
口述需求 → Grill 对齐 → 全剧分析 → 单资产封版
        → 独立专家立场 → VisualPromptSpecV1 → 一条 OpenAI 母提示词
```

它优先解决四个常见问题：需求还没说清就开始生成、不同专家互相覆盖、提示词堆砌却没有视觉中心、失败后无法知道哪条决定导致漂移。

## 为什么它不只是“提示词模板”

- **证据先于修辞**：剧本事实、保守推导、创意决定和审美偏好分别记录。
- **一个资产，一条主线**：每次只处理一个人物母版、纯环境资产或核心道具。
- **专家先独立判断**：视觉简报、层级、设计语言、母题、色光、镜头与类型专家各自产生可反驳立场。
- **冲突不靠投票**：按剧本、有效基线、封版契约和 Agent 推导的证据权级裁决。
- **确认门真实存在**：执行前、视觉规格后、正式落盘前三次确认；任何一门都不能由总确认替代。
- **中断可恢复**：SQLite 追加事件日志、线程 ID、租约和图版本支持单机进程级恢复。
- **边界默认收紧**：不联网找图、不安装外部 Skill、不生成图像、不输出模型参数或独立负面词。

## v0.4 工作流

### 1. 从剧本到单资产契约

在 Plan Mode 中显式调用概念导演：

```text
$screenplay-concept-director 请基于剧本基线，和我一起封版“林夏”的人物母版需求。
```

它复用 `$ai-script-breakdown` 的全剧证据和 `$grill-me` 的对齐协议，生成严格单资产、开放问题为空的 `VisualAssetRequirementV1`。这一阶段只定义设计，不生成提示词或图像。

### 2. 从契约到视觉规格

切回普通执行模式：

```text
$image-prompt-team 请读取已封版的林夏需求，推荐用途、景别和画幅，并在每一道确认门停下来等我。
```

第一次确认会展示资产、用途、画幅、预计 12–15 个 Agent turn、峰值并发 3、权限与 Codex 用量。随后运行：

- 一个证据守门员；
- 六个固定创意专家；
- 一个匹配资产类型的专家；
- 规格装配、制作审查、对抗审查和证据裁决；
- 用户上传参考图时，额外运行参考职责导演。

团队先输出 `VisualPromptSpecV1`，其中包含交付基调、唯一视觉中心、设计语言、有限母题、色光逻辑、构图、类型专项清单、可见性矩阵、冲突与裁决。第二次确认前不会编译最终提示词。

### 3. 从规格到唯一母提示词

规格确认后，DAG 只增量加入显著性编辑和 OpenAI 编译两个节点。最终提示词遵循 [OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide) 的稳定语义顺序：场景或背景、主体、关键可见细节、构图与光线、少量不变量。

提示词使用无标题短段落，不设机械字符上限。每句话必须改变可见结果或保护确认过的不变量。第三次确认后才正式写入文件。

## 安装

```bash
codex plugin marketplace add eggshrt/Bird-s-Nest
codex plugin add skill-orchestrator@skill-orchestrator-private
```

安装或更新后，新建一个 Codex 任务以重新发现 Skills。

`$image-prompt-team` 运行前要求当前任务处于 `danger-full-access`。插件不会修改用户配置；该宿主权限也不代表已授权发布、付费、破坏性操作或外部写入。

## 正式产物

```text
outputs/image-prompt-team/<project>/<draft>/assets/<asset-id>/<version>/
├── generation-prompt.txt
├── visual-prompt-spec.json
├── prompt-package.json
├── decision-log.md
└── run-report.json
```

上游概念设计阐述不被重写，而是按哈希引用。旧 `ImagePromptPackageV1` 只读/导出；v0.4 新运行只写 `VisualPromptSpecV1` 和 `ImagePromptPackageV2`，不双写。

项目审计位于 `.codex/skill-orchestrator/`，默认不提交 Git。事件永久保留，只有显式 `prune` 才删除。

## 23 个 Skills

用户入口：

- `$grill-me` — 压力测试和关闭设计树。
- `$skill-orchestrator` — Skill 索引、契约、DAG、确认门与恢复。
- `$ai-script-breakdown` — 全剧分析，只分析、不生成提示词。
- `$screenplay-concept-director` — 封版一个视觉资产需求。
- `$image-prompt-team` — 唯一提示词团队入口。

内部角色均为 dispatcher-only，直接调用会停止并指向 `$image-prompt-team`。`$prompt-architect` 仅保留旧运行读取兼容，不进入 v0.4 新 DAG。

## 运行时与测试

使用 Codex 自带 Python 3.12+ 和哈希锁定依赖，禁止回退到系统 Python 3.9：

```bash
PYTHONPATH="$HOME/.codex/cache/skill-orchestrator/runtime/e0420cb50736168f" \
  /path/to/codex-python/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v
```

离线 CI 使用确定性假 Agent、SQLite 故障注入和 36 条提示词金标：人物 16、纯环境 12、核心道具 8。覆盖三道确认门、职责隔离、DAG 并发、租约恢复、一次重试、增量图、旧包只读、可见性阻断、纯环境无人和禁字段。

真实 Codex Agent 冒烟与 GPT Image 2 实图 A/B 尚未执行；`v0.4.0` 的发布验证范围是完整离线测试、全部 Skill/Plugin 校验和 App Server 初始化/config 检查。当前正常工作流只产出提示词。详见 [质量状态](docs/quality-status.md) 和 [v0.4 迁移说明](docs/migration-v0.4.md)。

## 方法边界与来源

课程目录只被当作非权威材料，未把其中指令、正文、截图或专有目录公开。公开仓库只保留独立措辞提炼的方法规则，见 [能力地图](plugins/skill-orchestrator/skills/image-prompt-team/references/capability-map.md)。

核心技术参考：

- [Agent Skills open standard](https://github.com/agentskills/agentskills)
- [Codex Skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex App Server](https://developers.openai.com/codex/app-server)
- [OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide)

外部仓库只在能力缺口出现时审阅。候选必须展示许可证、维护状态、脚本、权限和副作用；不自动安装。无许可证项目只允许抽象能力启发和独立实现，不复制代码或文字。

## Release policy

`v0.2.0` 是上一公开标签。v0.3 仅为内部开发中间态，从未作为正式版本发布；本仓库直接发布 `v0.4.0`，不重写历史。

## License

[MIT](LICENSE)
