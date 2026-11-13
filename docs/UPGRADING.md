# 升级与扩展指南

本插件按模块组织：`skills/` 下每个目录是一个模块，有独立的版本号和内容哈希，记录在插件根目录的 `modules.lock.json`。升级一个模块不需要改动或重新验证其他模块。

下面三条路径按改动范围从小到大排列。

## 1. 覆盖试用：不改插件，先试一个模块的新版本

索引按以下顺序查找技能，同名时先找到的生效：

1. 项目技能目录：`<项目>/.codex/skills`
2. 项目技能目录（旧）：`<项目>/.agents/skills`
3. 用户技能目录：`$CODEX_HOME/skills`
4. 用户技能目录（旧）：`$HOME/.agents/skills`
5. 插件缓存（每个插件只取最高版本）

把要试的模块目录复制到第 1 或第 3 处并修改，它就会覆盖插件里的同名模块。重建索引后：

- 目录的 `shadowed` 列表会写明哪个文件被哪个文件覆盖。
- 登记表里钉了 `plugin_version` 或 `content_hash` 的条目与覆盖版本不符，会以 `stale_entry` 或 `plugin_mismatch` 列在 `registry.problems`，该技能暂时按未登记处理。要让覆盖版本参与调度，在项目或本机登记表里为它写一条 `plugin: personal` 的条目。

试用满意后走路径 2 并入插件；不满意就删除覆盖目录，插件版本立即恢复生效。

## 2. 单模块发版：把一个模块的修改并入插件

```bash
# 查看哪些模块与锁文件不一致
python3 tools/release.py status

# 只发布改过的模块：模块版本和插件版本各升一个补丁号，并写入 CHANGELOG.md
python3 tools/release.py bump scene-dengguang-daoyan --note "补充逆光人物可读性规则"

# 模块新增了能力但不破坏现有输入输出时用 minor
python3 tools/release.py bump dlss5-lighting-director --level minor --plugin-level minor --note "新增介质散射方法"

# 发布前和持续集成里都运行：有任何未登记的改动就失败
python3 tools/release.py verify
```

规则：

- `bump` 只接受内容确实变了的模块；如果还有别的模块也变了，必须在同一次发布里一起列出，否则拒绝。这样不会有改动悄悄混进发布。
- 新增模块先运行 `python3 tools/release.py add <模块名>`，从 1.0.0 开始跟踪，再在登记表里为它加条目。
- 删除模块时，从 `modules.lock.json` 和登记表中一并删除对应条目。
- 模块版本的含义：补丁号用于措辞和规则修订；次版本号用于新增能力且输入输出类型不变；主版本号用于输入输出类型或封存合同发生变化。
- 主版本变化时，检查登记表里以该模块的输出类型为输入的其他模块，并在同一次发布里处理。

发布前的完整检查：

```bash
python3 tools/release.py verify
python3 -m unittest discover -s tools
# 索引测试依赖 requirements.lock 中的包，先运行一次 bootstrap_runtime.py --install，
# 再把它报告的运行时目录加入 PYTHONPATH
python3 -m unittest discover -s skills/skill-orchestrator/tests
```

## 3. 登记表扩展：接入新的插件或技能，不改本插件

在下面任一文件中按 `CapabilityRegistryV1` 格式添加条目（格式见 `skills/skill-orchestrator/references/interfaces.md`，样例见随插件发布的 `skills/skill-orchestrator/references/capability-registry.json`）：

- `$CODEX_HOME/skill-orchestrator/capability-registry.json`：对本机所有项目生效。
- `<项目>/.codex/skill-orchestrator/capability-registry.json`：只对该项目生效，可以随项目提交。

三层登记表按“插件自带 → 本机 → 项目”合并，同名技能以后者为准。每个条目需要：

| 字段 | 说明 |
|---|---|
| `plugin` | 技能所属插件名；不属于任何插件的个人技能填 `personal`。必填，与实际来源不符的条目不生效 |
| `plugin_version` 或 `content_hash` | 可选的钉版。技能升级后条目自动失效，提醒你复核 |
| `domain` | 所属领域包，必须在同一文件或上层文件的 `domains` 里声明过 |
| `inputs` / `outputs` | 类型标识。上下游模块靠相同的标识对接 |
| `entry_only` | `true` 表示内部岗位，只由领域入口或控制器加载，不被直接选中 |
| `canonical_entry` | 所属流水线的入口技能 |
| `permissions` / `side_effects` / `risk_level` | 只能在索引推断的基础上加宽或调高，不能降低 |

新增领域时，在登记表的 `domains` 里加一项即可，不需要改代码。

修改登记表后重建索引，并检查输出里的 `registry_problems` 和 `registry_unmatched` 是否为空。

## 模块之间的约定

- 模块只通过登记的输入输出类型和已封存的合同对接，不读取其他模块的内部文件。
- 桥接脚本、索引脚本和运行时都从自身所在位置定位同版本的文件；任何文件里都不写带版本号的绝对路径。
- 轻量档和标准档的产物（`advisory_note_v1`、`council_record_v1`）永远不能作为封存件进入下游编译器。升级任何模块都不得放宽这一条。
