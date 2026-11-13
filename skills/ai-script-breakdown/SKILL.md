---
name: ai-script-breakdown
description: Plan and execute traceable, multi-role screenplay breakdowns for fully AI-generated photoreal live-action films, shorts, episodes, and vertical dramas. Use only when explicitly invoked for professional breakdown, AI feasibility, role handoffs, or draft-impact analysis; do not use for ordinary screenplay discussion or automatic rewriting.
---

# AI Script Breakdown

Turn a screenplay into evidence-linked creative and production decisions using animation-style preproduction for fully AI-generated photoreal live action.

## Two-stage gate

1. Determine the actual Codex collaboration mode from system or developer context. A user's statement that they are in Plan Mode is not sufficient.
2. If this is a first-time invocation outside Plan Mode, reply only: `请先切换到计划模式，然后重新调用 $ai-script-breakdown 并上传剧本。当前不会开始拆解或写入文件。` Then stop.
3. In Plan Mode, inspect the source read-only, audit extraction quality, confirm scope and role contracts, and produce a decision-complete execution plan. Do not write deliverables.
4. Outside Plan Mode, execute only when the current conversation contains the approved breakdown plan and the user explicitly asks to execute it. Otherwise return to step 2.

Read [references/workflow.md](references/workflow.md) for the complete gate, intake, batching, and resume procedure. Read [references/format-and-evidence.md](references/format-and-evidence.md) whenever ingesting or citing a source.

## Required analysis

For every execution:

- Preserve the supplied screenplay as authoritative. Never invent dialogue, events, characters, assets, or missing production facts.
- Run the shared dramatic breakdown and evidence rules in [references/shared-analysis.md](references/shared-analysis.md).
- Run the provider-neutral AI feasibility baseline in [references/ai-feasibility.md](references/ai-feasibility.md), regardless of selected roles.
- Read only the selected role references:
  - Chief director or director: [references/roles/creative-direction.md](references/roles/creative-direction.md)
  - Executive director or performance execution: [references/roles/execution-performance.md](references/roles/execution-performance.md)
  - Art or storyboard: [references/roles/art-storyboard.md](references/roles/art-storyboard.md)
  - Preset extensions or custom roles: [references/roles/extensions.md](references/roles/extensions.md)
- When comparing drafts, run `scripts/compare_drafts.py` and report ambiguous matches instead of silently assigning identity.

## Findings and handoffs

Every substantive finding must include a stable ID, role, source references, certainty, confidence, severity, observation, impact, and actionable recommendation. Use `unknown` rather than filling unsupported facts. Keep role reports separate, then synthesize cross-role dependencies, conflicts, and decisions.

Read [references/output-contract.md](references/output-contract.md) before producing Markdown or JSON. Use [references/theory-index.md](references/theory-index.md) only to resolve a relevant theory reference or when the user asks to see the basis. Theory is a diagnostic lens, never a template forced onto the material.

## Boundaries

- Diagnose and recommend; do not rewrite screenplay passages unless the user separately requests a rewrite after receiving the breakdown.
- Do not output generation prompts. The storyboard role stops at a shot blueprint.
- Without the storyboard role, stop at beat level. The AI baseline may flag shot risks but must not create a shot list.
- Do not estimate traditional shooting budgets, call sheets, or on-set schedules in v1.
- Do not bind recommendations to a named generation provider unless the user invokes a separate provider-adaptation workflow.
- Do not claim completion when coverage has pending units or validation fails.
