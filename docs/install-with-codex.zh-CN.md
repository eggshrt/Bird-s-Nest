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
5. 如果 marketplace 已存在，请不要创建重复项；改为刷新该 Git marketplace 后再安装或更新插件。
6. 安装完成后告诉我新建一个 Codex 任务，因为当前任务不会自动重新发现刚安装的 Skills。
7. 在最终回复中列出五个用户入口：`$grill-me`、`$ai-script-breakdown`、`$screenplay-concept-director`、`$image-prompt-team`、`$skill-orchestrator`，并给出一条最小启动示例。

如果任何命令失败，请保留原始错误，只进行只读诊断，不要手工编辑 marketplace.json 或 config.toml。
```

安装完成并新建 Codex 任务后，可以使用：

```text
$screenplay-concept-director 我会上传剧本和参考图。请先建立或复用全剧基线，只选择一个视觉资产，在每一道确认门停下来等我，不要生成图像。
```

若 marketplace 已安装而只需获取 GitHub 更新，可以让 Codex 执行：

```text
请刷新 `skill-orchestrator-private` Git marketplace，更新 `skill-orchestrator`，运行 `codex plugin list` 验证版本，然后提醒我新建任务加载更新后的 Skills。不要手工编辑任何 Codex 配置文件。
```
