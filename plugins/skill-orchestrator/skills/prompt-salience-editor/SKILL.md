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
