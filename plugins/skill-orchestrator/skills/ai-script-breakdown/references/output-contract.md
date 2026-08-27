# Output Contract

## Destination

Default to:

```text
<workspace>/outputs/ai-script-breakdown/<project-slug>/<draft-id>/
```

Use a user-specified destination when provided. Never overwrite a different draft silently.

## Files

```text
<draft-id>/
├── breakdown.md
├── breakdown.json
├── source-manifest.json
├── cross-role-decisions.md
└── roles/
    └── <role-id>.md
```

When comparing drafts, also create:

```text
draft-impact.md
draft-impact.json
```

## Markdown package

`breakdown.md` is the readable project-level report in Simplified Chinese by default:

1. 项目与覆盖状态
2. 核心判断
3. 结构、因果与信息设计
4. 人物、关系与表演链
5. 场景与节拍总表
6. AI 生成可行性基线
7. 问题与修改方向
8. 岗位交接摘要
9. 未知、假设、待确认与续跑锚点

Each selected role gets an independent `roles/<role-id>.md`. `cross-role-decisions.md` contains dependencies, conflicts, options, decision owner, required-by point, and current status.

## JSON package

`breakdown.json` must validate against `schemas/breakdown.schema.json` and contain:

- `schema_version`
- `project`
- `source_manifest`
- `coverage`
- `global_analysis`
- `entities`
- `scenes`
- `beats`
- `ai_feasibility`
- `role_reports`
- `issues`
- `cross_role_decisions`
- `theory_trace`
- `handoff`

Keep JSON keys in English. Preserve screenplay quotations in their source language.

## Finding contract

Every item in `issues` and every substantive `role_reports[].findings` item uses:

```json
{
  "id": "fnd-001",
  "role_id": "director",
  "source_refs": ["L12-L18"],
  "scene_ids": ["scn-002"],
  "beat_ids": ["bea-004"],
  "certainty": "explicit",
  "confidence": "high",
  "severity": "high",
  "observation": "Evidence-based observation",
  "impact": "Concrete downstream effect",
  "recommendation": "Actionable direction without replacement text",
  "theory_refs": ["TH-MCKEE-VALUE-CHANGE"]
}
```

`source_refs` may be empty only when `certainty` is `unknown`; then `scene_ids`, `beat_ids`, or a named role dependency must explain why the missing information matters.

## Coverage and status

`coverage` contains:

- `status`: `blocked | partial | completed`
- `requested_scene_ids`
- `completed_scene_ids`
- `pending_scene_ids`
- `requested_role_ids`
- `completed_role_ids`
- `pending_role_ids`
- `current_batch`
- `continuation_anchor`

Use `completed` only when all requested scenes, roles, the shared analysis, AI baseline, cross-role synthesis, and validation are complete. Otherwise use `partial` or `blocked`.

## Cross-role decisions

Each decision includes `id`, `topic`, `affected_role_ids`, `source_refs`, `conflict`, `options`, `recommended_option`, `decision_owner`, `required_by`, and `status`. Do not hide a disagreement by merging role prose.

## Draft impact

`draft-impact.json` validates against `schemas/draft-impact.schema.json` and records:

- High-confidence retained scene IDs.
- Added, removed, modified, and ambiguous scenes.
- Entity and asset changes.
- Affected role tasks and invalidated approvals.
- Required re-analysis scope.

The readable `draft-impact.md` summarizes the same facts. Ambiguous matches require review and must not retain IDs automatically.

## Validation

Run:

```bash
python3 scripts/validate_breakdown.py breakdown.json --markdown breakdown.md
```

Fix validation errors before reporting completion. If they cannot be fixed without user input, return `partial` or `blocked` with the exact missing decision.

