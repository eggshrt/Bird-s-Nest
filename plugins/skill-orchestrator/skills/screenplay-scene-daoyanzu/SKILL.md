---
name: screenplay-scene-daoyanzu
description: 将已验证的 screenplay_breakdown_v1 中同一剧本的 1–2 场转化为场景导演设计、表演调度、摄影分镜、连续性和现场执行包。仅用于用户明确要求场景导演、拍摄设计、表演调度、分镜、机位或现场执行方案；普通剧本分析、剧本改写、资产设计、图像生成和提示词任务不得触发。
metadata:
  tags: [screenplay, scene-direction, storyboard, blocking, continuity]
  input_types: [screenplay_breakdown_v1]
  output_types: [scene_direction_requirement_v1, scene_direction_package_v1, document, spreadsheet]
---

# 剧本场景导演组

把结构化剧本证据转化为可审定、可追踪、可现场执行的 1–2 场导演包。不得从原始剧本直接开始，也不得生成提示词或分镜图。

## 硬门槛

1. 只接受校验通过的 `screenplay_breakdown_v1`。scene、beat、evidence ID 不稳定时停止并引导先运行 `$ai-script-breakdown`。
2. 一次只能选同一剧本中的 1–2 个互不重复场景。
3. 先执行第一轮 Grill，封存 `CollaborationContextV1`、目标、受众、约束、岗位和验收标准。用户未确认前不得创建 DAG。
4. 使用现有 `ExecutionGraphV2`，`max_concurrency: 3`、`max_replans: 1`。常驻岗全部运行；条件岗由规则建议、总导演覆核、用户确认。
5. 岗位独立提案。真实冲突最多一次定向反驳；禁止循环辩论和投票。总导演给建议、代价与改变判断所需证据，用户拥有最终权力。
6. 第二轮 Grill 每次最多 3 个真实争议。零争议也要整体封存确认。确认前只能产出未封存草案，不能生成最终 DOCX 或显式兼容 XLSX。
7. 封存后任何实质修改必须派生新版本，不能覆盖旧版本。
8. 技术性错字、景别、机位、构图与摄影逻辑可在封存前直接斧正；对白、剧情、人物关系、身体接触、道具状态与核心走位的变化必须进入 Grill。

## 权威与边界

事实权威顺序：原剧本文本和稳定 evidence ID；当前已验证 breakdown；用户已确认决定；岗位专业推断。岗位不得改写前三者。高影响岗位缺失阻断封存；低影响缺失可由总导演临时覆盖，但须记录低置信度和复核条件。

常驻岗：`scene-zongdaoyan`、`scene-biaoyan-diaodu-daoyan`、`scene-sheying-fenjing-daoyan`、`scene-lianxuxing-zhixing-daoyan`。

条件岗：`scene-dongzuo-daoyan`、`scene-taici-daoyan`、`scene-dengguang-daoyan`、`scene-tiaose-daoyan`、`scene-shengyin-daoyan`、`scene-texiao-daoyan`、`scene-chuangyi-daoyan`。创意岗权重最低，不得覆盖事实、安全或用户决定。蒙太奇和空镜由摄影分镜导演与总导演共同负责。

## 工作流

完整流程、激活规则、接口和交付规范分别见 [workflow.md](references/workflow.md)、[role-activation.md](references/role-activation.md)、[interfaces.md](references/interfaces.md) 与 [output-contract.md](references/output-contract.md)。研究采用与排除记录见 [research-benchmarks.md](references/research-benchmarks.md)。

运行确定性校验与旧格式兼容物化：

```bash
python3 scripts/scene_director.py validate-requirement requirement.json --breakdown breakdown.json
python3 scripts/scene_director.py validate-package scene-direction-package.json --breakdown breakdown.json
python3 scripts/scene_director.py materialize scene-direction-package.json --docx legacy-director-package.docx
python3 scripts/scene_director.py materialize scene-direction-package.json --docx legacy-director-package.docx --xlsx legacy-shot-list.xlsx
```

新默认流程先封存 `SceneDirectionPackageV1`，再调度 `$screenplay-shot-prose-compiler` 生成“一镜一段”的中文 DOCX。只有旧调用显式要求 XLSX 时才进入兼容路径。

## 禁止输出

- 生成式图像、分镜图、提示词、负面提示词、模型参数。
- 角色、场景、道具资产重新设计。
- 预算、排期、通告单或完整制片计划。
- 未经用户确认的对白、事实、动作或剧情变化。
