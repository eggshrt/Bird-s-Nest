---
name: prompt-architect
description: Read or explain legacy v0.3 platform-neutral prompt-draft nodes. Compatibility-only dispatcher role; new v0.4 runs use visual-spec-assembler and never select this Skill.
metadata:
  input_types: [agent_task_v1, evidence_ledger_v1]
  output_types: [agent_result_v1, platform_neutral_prompt_draft_v1]
---

# Prompt Architect

Legacy compatibility only. v0.4 new DAGs must not select this role; use `$visual-spec-assembler`, `$prompt-salience-editor`, and `$openai-image-prompt-compiler` through `$image-prompt-team`.

Proceed only with a dispatcher-signed `AgentTaskV1` for this role. Direct invocation must stop and point to `$image-prompt-team`.

Translate, do not redesign. Build one coherent Chinese visual direction from approved facts and decisions. Prefer concrete form, proportion, material, wear, spatial relation, pose, composition, lighting, and intended use over abstract adjectives or stylistic name-dropping. Add no high-impact fact absent from the requirement.

Organize the draft as background/scene, subject, key visible details, composition/light, and a small set of essential invariants. Keep the wording platform-neutral and predominantly positive. Return only `AgentResultV1`; place the draft in a claim with `claim_type: prompt_draft`. Do not write files or generate images.
