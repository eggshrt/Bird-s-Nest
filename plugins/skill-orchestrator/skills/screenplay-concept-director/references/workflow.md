# Workflow

## Stage 0: mode and scope gate

- Require explicit `$screenplay-concept-director` invocation.
- Outside Plan Mode, emit the exact stop message from `SKILL.md` and do nothing else.
- In Plan Mode, accept one screenplay or an existing `breakdown.json`, an intended asset name/id, and optional user-supplied reference images.
- Do not search the web for references unless the user separately requests and authorizes that research.

## Stage 1: baseline preflight

Run `freshness` against the current breakdown. A usable baseline must have:

- `coverage.status == completed`;
- AI baseline and cross-role synthesis completed;
- no pending scenes or roles;
- completed `chief_director`, `director`, `performance_execution`, and `art` role reports;
- the same normalized screenplay source hash and bundled analyzer hash.

If no baseline exists or it is stale, use sibling `$ai-script-breakdown`. Text, Markdown, Fountain, and FDX use its normalizer. PDF and DOCX require layout-aware extraction with page/paragraph anchors before normalization.

Do not begin asset alignment from a partial baseline. A user may explicitly end the run instead of refreshing, but may not waive evidence completeness and still receive a confirmed contract.

## Stage 2: catalog and selection gate

Generate `asset-catalog.json` and `asset-catalog.md`. Catalog types are fixed:

| Type | Source |
| --- | --- |
| `character_master` | `entities.characters` |
| `location_master` | `entities.locations` |
| `scene_state` | `scenes` |
| `hero_prop` | `entities.props` |

Resolve the user's spoken name against ids, names, and aliases. Always show the selected candidate's id, type, evidence, and competing same-name candidates. The resolver may recommend a unique candidate but never confirms it for the user.

Gate 1 closes only when the user confirms one exact stable id.

## Stage 3: fresh context snapshot

Create a new snapshot after Gate 1. Include:

- project/draft/source/analyzer fingerprints;
- story contract, character system, theme/value system, world rules, continuity, and AI feasibility;
- the complete selected asset catalog record;
- its referenced scenes, beats, and relevant role findings;
- inclusion and omission counts.

Exclude the full screenplay body and unrelated scene prose. When relevant material is too large, synthesize contiguous evidence batches, preserve source refs, and list omitted ids. Never fill omissions from chat memory.

## Stage 4: evidence-led Grill

Create a design tree from the shared and type-specific dimensions. Ask the entire current frontier, at most three questions per round.

For a user who does not know what they want:

1. quote or summarize the decisive evidence with source refs;
2. translate it into two or three observable visual directions;
3. explain narrative, cultural, continuity, and production consequences;
4. state the director's preferred direction;
5. let the user accept, modify, or reject it.

One primary state is required. Derived states must use the same asset id, declare `delta_from`, and contain changes rather than a second full design. Let the user prune them.

Gate 2 closes only when high-impact decisions are accepted or explicitly overridden, `open_questions` is empty, and the user confirms the shared design requirement.

## Stage 5: persistence gate and execution

Before Gate 3, show:

- exact artifact paths;
- baseline and context hashes;
- files to be written;
- semantic and schema validators;
- reference-image handling;
- the explicit exclusion of prompts, model parameters, providers, image generation, and additional assets.

After Gate 3, validate and materialize. Default to serial execution. Record failures and retry only the affected validation/materialization step once.
