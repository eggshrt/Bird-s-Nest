# Workflow

## Modes and recovery

Require explicit `$screenplay-concept-director` invocation. These business-run gates do not govern maintenance or auditing of the skill itself.

Plan Mode permits read-only input inspection and design/planning in chat. Do not run commands that create catalogs, snapshots, checkpoints, or final packages there. If baseline analysis is needed, present the upstream execution plan and retain `baseline_pending`; execute it in Default Mode after the user authorizes it. Do not bypass the upstream's own mode rules.

Default Mode accepts a new user-authorized execution or an explicit resumption. Drafts, catalogs, snapshots, scratch analysis, and role work stay under `work/`; `outputs/` receives only the final Chinese design book. They are drafts and do not imply any of the three confirmations. A mode change alone grants no authorization. Do not add a fourth routine approval when the user's existing instruction already authorizes this work.

Resume from disk inputs, draft requirement, snapshot, creative position, and actual user confirmation messages. Revalidate freshness and confirmation digests before trusting a checkpoint. Conversation may prove a confirmation, but never substitutes for project evidence. If a reference or bound content is missing or changed, reopen the affected gate and its successors.

The resumable states are `baseline_pending → baseline_ready → asset_confirmed → design_confirmed → persistence_approved → materialized`. Inspection and discussion may occur in either mode; disk mutations occur only in authorized Default execution. Three distinct user decisions remain mandatory.

## Stage 1: baseline preflight

Use sibling `$ai-script-breakdown` as the only analysis upstream. `freshness` must verify the source on disk and invoke upstream validation. A usable baseline has:

- `coverage.status == completed`, AI baseline and cross-role synthesis completed;
- no pending scenes or roles, with completed `chief_director`, `director`, `performance_execution`, and `art` reports;
- `source_manifest.analysis_provenance` containing `analyzer_hash`, `source_hash`, `source_path`, and `captured_at`, recorded at analysis intake;
- matching current source and analyzer fingerprints and valid coverage references.

An unreadable source is unverified, not fresh. A missing intake provenance record requires reanalysis; rebuilding a catalog or adding today's hashes to old output cannot repair provenance. Text, Markdown, Fountain, and FDX use the upstream normalizer. PDF and DOCX require layout-aware extraction with page/paragraph anchors before normalization.

Do not begin confirmed asset alignment from a partial baseline. The user may end the run instead of refreshing, but cannot waive evidence completeness and still receive a confirmed contract.

## Stage 2: catalog and selection gate

Create the catalog JSON as a working artifact in Default Mode. Do not create catalog Markdown unless the user requests it. Its types come from the baseline:

| Type | Source |
| --- | --- |
| `character_master` | `entities.characters` |
| `location_master` | `entities.locations` |
| `scene_state` | `scenes` |
| `hero_prop` | `entities.props` |

Resolve ids, names, and aliases. Show stable id, type, evidence, and competing same-name candidates. The resolver may recommend a candidate but cannot confirm it. Prepare the baseline reference from the catalog before binding Gate 1. The selection digest excludes `context_hash`, which is established by the subsequent snapshot and bound by Gate 2.

Gate 1 closes only on the user's confirmation of the exact subject and baseline. Record the actual message reference and `confirmation-digest --gate asset_selection` result. Do not invent approval records.

## Stage 3: fresh context snapshot

Create a new snapshot from disk for the selected subject. It includes:

- project/draft/source/analyzer fingerprints and `baseline_files.breakdown_path` / `source_path`;
- story contract, character system, theme/value system, world rules, continuity, and AI feasibility;
- the complete catalog identity and all selected-asset scene, beat, and role-finding evidence;
- relevant `cross_role_decisions`, `issues`, and `handoff` information, including blockers;
- `evidence_completeness` status and explicit omission accounting.

Exclude the full screenplay body and unrelated scene prose. Never take the first N records or silently omit a later scene. If the supported evidence budget is exceeded, stop before approval/handoff and report the affected evidence and budget. The snapshot CLI permits explicit `--max-scenes`, `--max-beats`, `--max-findings`, and `--max-context-bytes` adjustments when the entire resulting snapshot remains reviewable; increasing limits must not introduce omissions. A future explicit batching implementation may summarize with source traceability, but this version must not claim an unimplemented summarization fallback. Freshness alone does not establish evidence completeness.

## Stage 4: evidence-led Grill

Load sibling `$grill-me` and build the dependency tree from shared and type-specific dimensions. Ask at most three questions from the current frontier per round, ordered by consequence; preserve additional frontier branches for later. Do not reopen answers already established by evidence or an explicit user decision.

For an undecided user, show decisive evidence with source refs, two or three observable choices, their consequences, and one director recommendation. Let the user accept, modify, or reject it. Unsupported facts remain `unknown`. Consequential unknowns block completion; a genuinely irrelevant dimension may be `not_applicable` with an explicit reason.

One primary state is required. Derived states share its asset id, declare `delta_from`, and contain changes rather than a second design. Let the user prune them. Read-only dependencies use `dependency_assets` with `ref_asset_id`, type, version, requirement path, and hash; never redesign them within this run.

For `location_master` and `scene_state`, `$image-prompt-team` accepts only `output_scope: pure_environment`. Scene participants and power relations remain evidence/context, not output subjects. If the user requested visible participants, action, or dramatic blocking, explain the scope mismatch and route that work to `$screenplay-scene-daoyanzu`; do not silently turn it into an empty environment. A pure-environment extraction from a broader scene requires the user's explicit scope choice.

Maintain one canonical requirement and creative-position record as the interview progresses. Apply focused deltas to answered dimensions; do not rewrite or repaste the full contract each round. Gate 2 closes when all consequential dimensions are resolved, high-impact decisions are `accepted` or `user_override`, `open_questions` is empty, and the user confirms the exact design plus creative position. Preserve the original recommendation, the user's overriding choice, and its consequences. Bind the confirmation to the script-generated design digest.

## Stage 5: persistence gate and execution

After Gate 2, prepare the exact `persistence_plan`. New runs set `output_root` under `work/screenplay-concept-director` and `design_book_path` to the single public `资产概念设计书.md` under `outputs/`; see the output contract for full paths. Show the book destination, a concise list of internal package paths and their purpose, validators, reference-image handling, risks, and exclusions. Internal files are necessary for validation and downstream handoff; do not describe the system as physically storing only one file. Gate 3 separately approves both destinations and their bound content. There is no additional approval gate.

In Default Mode, `seal` computes integrity only; it never confirms a gate. Recheck strict validation, current disk provenance, and dependency hashes. The materializer renders the Chinese book directly from canonical data, atomically commits the internal six-file package, then atomically publishes the book at its approved path. It does not invoke an LLM to write another version. If publication fails after the internal commit, preserve that complete package and retry the same approved inputs; do not invent a new version or overwrite different public content.

Changed design invalidates Gate 2 and Gate 3; changed identity/baseline invalidates all three; changed internal root or public book path invalidates Gate 3. Never recalculate an old approval to make changed content pass. Legacy sealed revision-2 packages without `design_book_path` retain their existing six-file layout and locations; do not relocate or retrofit them automatically.

Retry only the affected validation/materialization step once. Any repair that changes approved content first requires renewed affected approvals. On a second failure, stop and report the failing stage. Record observable validation evidence in the parent `RunReportV2` internally when applicable. Default CLI output reports the public deliverable and validation status; automation may request `--details` for internal artifact paths and `machine_handoff`. The user-facing final reply contains the book link, with no backend file list or extra audit report.

## Efficient reuse

The public book is a complete Chinese design document: approved direction, all design dimensions and states, the director's full position and tradeoffs, user overrides, acceptance criteria, confirmation summary, and a folded evidence appendix. Runtime metadata is not repeated in role prompts. Role projections retain all evidence and creative constraints and remain tied to the validated canonical contract; they never replace that contract for handoff validation.

Use script-generated hashes and deterministic Markdown rendering. Do not generate duplicate prose, introduce JSONL or SQLite as new deliverables, or claim gzip/base64 reduces model token use. The internal package depends on its referenced source, breakdown, reference images, and dependency files; it is not portable merely because its six files were copied.
