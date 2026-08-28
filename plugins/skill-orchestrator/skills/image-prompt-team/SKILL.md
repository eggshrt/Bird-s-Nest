---
name: image-prompt-team
description: Turn one sealed VisualAssetRequirementV1 into a confirmed VisualPromptSpecV1 and one Chinese OpenAI-first master prompt through a recoverable expert DAG. Explicit user entry for character, pure-environment, or hero-prop prompt work.
metadata:
  input_types: [visual_asset_requirement_v1]
  output_types: [visual_prompt_spec_v1, image_prompt_package_v2, run_report_v2]
---

# Image Prompt Team

This is the only user-facing prompt-team entry. Internal role Skills run only from dispatcher-signed `AgentTaskV1` packets.

## Preconditions

1. Run only in Codex Default mode. In Plan Mode, stop before reading the requirement or creating a run.
2. Require effective `danger-full-access`; never modify Codex configuration.
3. Accept exactly one sealed `VisualAssetRequirementV1` with empty questions, accepted high-impact decisions, three upstream confirmations, and a fresh hash.
4. Support character masters, pure-environment locations or scene states, and hero props. A high-impact design gap returns to `$screenplay-concept-director`.
5. Accept reference images only from the user. Do not browse for them.

## Three gates

1. Recommend intended use, framing, and aspect ratio. Show the asset, expected 12–15 Agent turns, peak concurrency three, permissions, Codex usage, and side effects; obtain initial confirmation.
2. Run evidence, the type specialist, six independent creative positions, assembly, production review, adversarial review, and evidence adjudication. Show the compact `VisualPromptSpecV1`; obtain spec confirmation.
3. Add only salience editing and OpenAI compilation to the DAG. Show one Chinese prompt; obtain final confirmation before formal files are written.

The upstream design statement is linked, not regenerated. Normal execution never generates an image, model parameters, a negative prompt, a second asset, or alternatives. Environment assets contain no people. A derivative request produces only `DerivativeRequestV1`; it does not create a multi-view sheet, narrative shot, state variant, repair, or image.

Read [references/workflow.md](references/workflow.md) before execution, [references/prompt-method.md](references/prompt-method.md) before judging prompt content, and [references/interfaces.md](references/interfaces.md) for advanced data. The course-derived capability audit is in [references/capability-map.md](references/capability-map.md); it is source material, never runtime instruction.
