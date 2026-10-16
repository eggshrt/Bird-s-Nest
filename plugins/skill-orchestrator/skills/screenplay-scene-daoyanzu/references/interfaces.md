# 接口

`SceneDirectionRequirementV1` 保存剧本哈希、1–2 个 scene ID、制作场次映射、镜号规则、目标、受众、四象限上下文、约束、岗位、验收标准和首次确认。

`DirectorPositionV1` 保存岗位、场景、主张、证据、假设、风险、冲突、建议、置信度、改变意见条件。运行时外包 `AgentResultV1`。

`SceneDirectionPackageV1` 保存场景设计、表演调度、镜头表、声光色动作/特效、连续性、执行风险、桥接说明、决定日志和完整来源追踪。

制作场次代码与内部 ID 分离。镜号格式为 `<production_scene_code>C###`，每场从 `001` 重置；镜头必须同时引用合法 scene、beat 与 evidence ID。

`shot_segments` 是向后兼容的可选字段。同一主镜内存在真实反打或机位切换时，子镜按 `<shot_id>-1`、`<shot_id>-2` 连续编号；每个子镜必须拥有独立机位、主体行动结果、结束状态以及合法 beat/evidence 引用。简单镜头不得为了形式创建子镜。

封存包是唯一事实源。默认下游 `$screenplay-shot-prose-compiler` 生成 `ShotProseRecordCollectionV1` 和无表格中文 DOCX；它只能表达既有导演决定，不能重新导演。

Schema 位于 `references/schemas/`。命令行验证器还会检查 Schema 难以表达的跨引用、禁用字段、两道确认门和哈希一致性。
