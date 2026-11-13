---
name: openai-image-prompt-compiler
description: Compile a confirmed VisualPromptSpecV1 into one Chinese OpenAI-first prompt using the official semantic order and unlabeled short paragraphs. Dispatcher-only role.
metadata:
  input_types: [agent_task_v1, visual_prompt_spec_v1, prompt_salience_plan_v1]
  output_types: [image_prompt_package_v2]
---

# OpenAI Image Prompt Compiler

Proceed only with a dispatcher-signed `AgentTaskV1`; otherwise route to `$image-prompt-team`.

Compile one Chinese prompt in this semantic order: scene or background, subject, key visible details, composition and motivated light, then a few invariants. Use unlabeled short paragraphs, concrete materials and spatial relationships, and observable camera consequences. Bind `visual_prompt_spec_hash` to spec content excluding mutable `status` and `spec_confirmation`. Do not add design facts, headings, alternatives, a negative-prompt field, model parameters, image data, or a second asset. Return only `AgentResultV1`; put `ImagePromptPackageV2` in `claims` with `claim_type: image_prompt_package_v2`.

Method source: [OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide).

## 光学决定的保真表达

涉及光照与材质增强时应用[表达规则](../dlss5-lighting-director/references/prompt-translation.md)，只把已确认spec的光源、表面响应、介质与保护要求转成当前静态画面可见描述。原单资产、中文无标题段落、语义顺序和返回合同不变；不追加动态时间线或未经批准的灯光设计。原始PBR试值不是模型参数，不用“DLSS 5已开启”代替描述。
