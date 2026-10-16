# Output contract

## One public book, an internal machine package

For every new run, the approved persistence plan uses these defaults:

```text
persistence_plan.output_root:
  <workspace>/work/screenplay-concept-director/

persistence_plan.design_book_path:
  <workspace>/outputs/screenplay-concept-director/<project-id>/<draft-id>/assets/<asset-id>/<version>/资产概念设计书.md
```

`design_book_path` must be an absolute `.md` path separate from the internal root. Its presence opts into single-book publication, and Gate 3 binds this exact path. There is no separate CLI override for the public destination. The final reply links only this book.

Drafts, scratch files, role work, and project-level catalog caches remain under `work/`. Do not create catalog Markdown unless the user requests it. The script renders the Chinese design book directly from approved canonical data: direction, all design dimensions and states, the full director position and tradeoffs, user overrides, production and cultural constraints, invariants, exclusions, acceptance criteria, confirmation summary, and a folded evidence appendix. Do not generate another prose version or a separate user-facing audit report.

The machine handoff remains six files, stored internally for validation and downstream compatibility:

```text
<output_root>/<project-id>/<draft-id>/assets/<asset-id>/<version>/
├── context-snapshot.json
├── requirement.json
├── requirement.md
├── creative-position.json
├── decision-log.md
└── asset-catalog.json
```

`persistence_plan.files` remains exactly `["context-snapshot.json", "requirement.json", "requirement.md", "creative-position.json", "decision-log.md", "asset-catalog.json"]`; `validators` remains `['schema', 'semantic', 'disk_freshness']`. The public book is declared separately by `design_book_path`, not added to that compatibility list. Internal Markdown views are deterministic script output, not additional model-written deliverables.

Before Gate 3, show the single public book destination and briefly disclose the internal package location and six filenames, their validation purpose, reference-image handling, risks, and exclusions. Do not claim the system physically stores only one file. Reference-image links do not imply permission to download, transform, or redistribute them.

## Commit, retry, and compatibility

After all three current confirmations, the materializer validates the exact approved destinations, renders all contents, commits the complete internal directory atomically, and then atomically publishes the public book. It never overwrites different content. A failure before internal commit exposes no partial version. A failure during book publication may leave a complete internal package; retrying identical approved inputs reuses that package and completes publication. Do not create another version merely to recover an interrupted publish.

A changed internal root, public book path, or validator plan requires a new persistence confirmation. A changed package version or design requires updated design and persistence confirmations. Keep actual user message references; helpers never approve on the user's behalf.

Existing sealed revision-2 packages without `design_book_path` remain readable, validatable, and usable for downstream handoff at their existing locations. If their approved version directory does not yet exist, materialization uses the legacy six-file layout. Do not relocate or retrofit completed packages. An exact byte-identical package is safe to retry; an older renderer may have produced different Markdown, in which case rematerialization rejects rather than rewrites it. Continue using that already completed package as-is; different or incomplete content is never overwritten.

The package is not portable by copying its six files: validation still needs its original source, breakdown, reference images, and dependency requirements at their recorded paths. The book is the user-readable result; downstream automation uses the internal sealed requirement and companions.

## Commands

Commands that write files run only in authorized Default Mode. Keep canonical draft records in `work/`, update them with focused deltas, and use the script for hashes and all Markdown rendering.

```bash
python3 scripts/concept_director.py freshness \
  --breakdown <breakdown.json> \
  --source <intake-source>

python3 scripts/concept_director.py catalog \
  --breakdown <breakdown.json> \
  --output <work/asset-catalog.json>

python3 scripts/concept_director.py resolve \
  --catalog <work/asset-catalog.json> \
  --query '<asset name or id>'

python3 scripts/concept_director.py snapshot \
  --breakdown <breakdown.json> \
  --catalog <work/asset-catalog.json> \
  --asset-id <stable-id> \
  --output <work/context-snapshot.json>

python3 scripts/concept_director.py confirmation-digest \
  --requirement <work/requirement.json> \
  --gate <asset_selection|design_requirement|persistence_plan>

python3 scripts/concept_director.py seal \
  --requirement <work/requirement.json> \
  --snapshot <work/context-snapshot.json> \
  --position <work/creative-position.json> \
  --output <work/sealed-requirement.json>

python3 scripts/concept_director.py validate-requirement \
  --requirement <work/sealed-requirement.json> \
  --snapshot <work/context-snapshot.json> \
  --position <work/creative-position.json>

python3 scripts/concept_director.py materialize \
  --catalog <work/asset-catalog.json> \
  --snapshot <work/context-snapshot.json> \
  --requirement <work/sealed-requirement.json> \
  --position <work/creative-position.json> \
  --output-root <approved-internal-output-root>
```

By default, materialization reports the public `deliverables` plus status, identity, and validation summary. Add `--details` only when automation needs internal `artifacts` and `machine_handoff`; do not copy those backend lists into the final user reply. Legacy runs without a public path retain their internal package; the new-run book requirement does not change old approvals.

Before design confirmation, establish the creative-position hash so Gate 2 covers it. Use the script's `content_hash` canonicalization for content hashes and `requirement_hash` for dependency hashes; a raw file-byte hash is not interchangeable. `seal` never manufactures or rewrites confirmations. If hashed content changes, reopen the affected gate.

`validate-requirement` requires both sidecars, checks structure and semantic links, and rechecks current source/baseline/analyzer and dependency files. Structural validation uses the supported JSON Schema subset in `scripts/contract_schema.py`; unsupported validation keywords fail closed. It is not a general Draft 2020-12 engine. The V2 parent records validation evidence internally in its own `RunReportV2`.

Do not introduce JSONL/SQLite as new deliverables or compress/encode JSON merely to claim model token savings. Downstream role projections may remove runtime metadata while retaining all creative evidence and constraints; the sealed canonical data remains the validation authority.
