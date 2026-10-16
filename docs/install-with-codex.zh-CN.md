# 让 Codex 从 GitHub 安装 Bird's Nest

把下面整段复制到一个新的 Codex 任务中。它会让 Codex 使用官方插件 CLI 添加 GitHub marketplace、安装 `skill-orchestrator`、核对结果，并告诉你何时需要新建任务以加载 Skills。

```text
请从 GitHub 安装 Bird's Nest / Skill Orchestrator 插件，并完成只读验证。

仓库：https://github.com/eggshrt/Bird-s-Nest
Marketplace 来源：eggshrt/Bird-s-Nest
Marketplace 名称：skill-orchestrator-private
插件名称：skill-orchestrator

请按以下顺序执行：

1. 先运行 `codex plugin marketplace add eggshrt/Bird-s-Nest`。
2. 再运行 `codex plugin add skill-orchestrator@skill-orchestrator-private`。
3. 运行 `codex plugin list`，确认 marketplace 与插件都能被发现，并报告实际安装版本。
4. 不要修改 Codex 配置文件，不要安装仓库之外的依赖，不要运行任何图像生成，也不要访问我的项目文件。
5. 如果 marketplace 已存在，请不要创建重复项；运行 `codex plugin marketplace upgrade skill-orchestrator-private`，再执行安装命令并验证实际版本。
6. 安装完成后告诉我新建一个 Codex 任务，因为当前任务不会自动重新发现刚安装的 Skills。
7. 在最终回复中说明剧本拆解、场景导演和分镜 Word 主流程，以及单资产图片提示词和显式 Seedance 提示词两个分支；入口与输入输出以 README 为准。

如果任何命令失败，请保留原始错误，只进行只读诊断，不要手工编辑 marketplace.json 或 config.toml。
```

安装完成并新建 Codex 任务后，先切换到计划模式，再上传剧本并使用：

```text
$ai-script-breakdown 请先检查我上传的剧本，和我确认分析范围及岗位，制定剧本拆解计划。先不要执行或写入交付文件。
```

若 marketplace 已安装而只需获取 GitHub 更新，可以让 Codex 执行：

```text
请运行 `codex plugin marketplace upgrade skill-orchestrator-private`，再运行 `codex plugin add skill-orchestrator@skill-orchestrator-private`，最后运行 `codex plugin list` 验证实际版本，并提醒我新建任务加载更新后的 Skills。不要手工编辑任何 Codex 配置文件。
```
