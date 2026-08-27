# Workflow

## Purpose

This workflow separates read-only planning from deliverable creation. It applies animation-style preproduction discipline to fully AI-generated photoreal live action.

## Stage 0: Mode gate

- Trust only the current system/developer collaboration-mode context.
- First invocation outside Plan Mode: show the exact switch-mode message from `SKILL.md` and stop. Do not inspect the screenplay, run parsers, or create files.
- Invocation in Plan Mode: continue to intake. All inspection must remain read-only; parser output goes to stdout, not a file.
- Execution outside Plan Mode is allowed only after a decision-complete plan exists in the same conversation and the user explicitly authorizes execution.

## Stage 1: Intake in Plan Mode

Require the screenplay as pasted text or a TXT, Markdown, Fountain, FDX, PDF, or DOCX file. Collect or infer without inventing:

- Project title and stable project ID.
- Draft ID and, for comparisons, the previous draft.
- Format: feature, short, episode, or vertical drama.
- Target duration, aspect ratio, and source language when known.
- Requested scope: full script, act, sequence, scene range, or named scene IDs.
- One or more roles from the built-in menu.
- Desired diagnosis depth. Default is diagnosis plus revision direction, without rewriting.

Always show the built-in menu:

| Role ID | 中文岗位 | Purpose |
| --- | --- | --- |
| `chief_director` | 总导演 | Global creative alignment and priorities |
| `director` | 导演 | Scene interpretation, staging, performance, sound, and time |
| `executive_director` | 执行导演 | Generation tasks, dependencies, risks, and handoffs |
| `performance_execution` | 演出执行 | Playable action, timing, gaze, lip sync, and body continuity |
| `art` | 美术 | World, character, location, costume, prop, and style assets |
| `storyboard` | 分镜 | Shot blueprint without generation prompts |

Offer preset extensions from `roles/extensions.md` and allow a custom role.

For a custom role, draft a responsibility contract containing `role_id`, `display_name`, `objective`, `questions`, `deliverables`, `dependencies`, and `exclusions`. Do not execute that role until the user confirms the contract.

## Stage 2: Source audit in Plan Mode

Read `format-and-evidence.md`. For text-native formats, run:

```bash
python3 scripts/normalize_screenplay.py <source> --source-id <id> --draft-id <id>
```

Omit `--output` in Plan Mode so the result stays on stdout.

For PDF or DOCX, use the installed Codex PDF or Documents capability, preserve page/paragraph anchors, then feed extracted plain text to the normalizer through stdin. If the required capability is unavailable, stop and identify the missing dependency.

Report:

- Detected format and extraction quality.
- Script fingerprint, scene count, source-reference scheme, and warnings.
- Ambiguous or missing scene boundaries.
- OCR corruption, lost dialogue attribution, unreadable pages, or unsupported layout.
- Coverage proposed for the execution run.

Block execution when extraction quality is `failed`. For `degraded`, explain the risk and require explicit acceptance in the plan.

## Stage 3: Decision-complete plan

The plan must lock:

- Source and draft identifiers.
- Selected scope, roles, and confirmed custom-role contracts.
- Whether draft comparison is included.
- Batch boundaries for long material.
- Output destination and expected files.
- Extraction warnings accepted by the user.
- Tests and completion criteria.

Do not perform the actual breakdown or write output files in Plan Mode.

## Stage 4: Execution

After the user exits Plan Mode and explicitly authorizes execution:

1. Normalize the source and persist `source-manifest.json`.
2. If supplied, compare the prior draft and preserve high-confidence scene IDs.
3. Run shared analysis for the approved scope.
4. Run the AI feasibility baseline.
5. Run selected role packs only.
6. Produce independent role reports.
7. Synthesize cross-role decisions, conflicts, blockers, and dependencies.
8. Write the Markdown and JSON package defined by `output-contract.md`.
9. Run `scripts/validate_breakdown.py`; do not mark the run complete on failure.

## Long scripts and continuation

- Batch by explicit act/sequence boundaries when present; otherwise use contiguous scene ranges.
- Never split inside a dialogue exchange or dramatic beat merely to hit a size target.
- Keep a coverage ledger with `requested`, `completed`, `pending`, and `current_batch` IDs.
- Preserve existing scene, beat, entity, finding, and decision IDs across continuation.
- Complete the current batch fully. If context is insufficient, return `partial` with a visible continuation anchor: `▶ CONTINUE FROM: <scene-or-batch-id> <label>`.
- Never summarize untouched scenes as if they were analyzed.

## Stop conditions

Stop and report a blocker when:

- No screenplay source is available.
- Extraction quality prevents reliable evidence references.
- A custom role has no confirmed contract.
- Draft matching is ambiguous enough to risk incorrect ID retention.
- The requested scope exceeds available context and no clean batch boundary is possible.
