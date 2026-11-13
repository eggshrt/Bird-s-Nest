---
name: prompt-salience-editor
description: Rank, deduplicate, and prune a confirmed VisualPromptSpecV1 by visible impact and invariant protection before prompt compilation. Dispatcher-only role.
metadata:
  input_types: [agent_task_v1, visual_prompt_spec_v1]
  output_types: [prompt_salience_plan_v1]
---

# Prompt Salience Editor

Proceed only with a dispatcher-signed `AgentTaskV1`; otherwise route to `$image-prompt-team`.

Treat prompt budget as attention, not character count. Keep a sentence only if it changes a visible result or protects a confirmed invariant. Remove duplicates, adjective stacks, implementation trivia, weak camera numerology, and low-priority spectacle. Preserve all confirmed high-impact content and at most three final exclusion clauses. Return only `AgentResultV1`; put `PromptSaliencePlanV1` in `claims` with `claim_type: prompt_salience_plan`, not the final prompt.

光源—表面—角度/遮挡—运动响应是可见结果约束，不是可随意删除的技术赘述。按[光学表达规则](../dlss5-lighting-director/references/prompt-translation.md)去掉重复品牌、数值与形容词，但保留使材料有区别、状态不矛盾的关键因果和身份保护。不要把已确认光学决定压缩成“DLSS 5、真实反射、电影感”。
