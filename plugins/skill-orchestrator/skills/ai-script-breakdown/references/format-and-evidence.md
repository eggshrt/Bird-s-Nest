# Format and Evidence Rules

## Supported input routes

| Input | Route | Evidence anchor |
| --- | --- | --- |
| Pasted text, TXT, Markdown | `normalize_screenplay.py` | `L<start>-L<end>` |
| Fountain | `normalize_screenplay.py` | `L<start>-L<end>` plus scene number when present |
| FDX | `normalize_screenplay.py` | `P<start>-P<end>` for Final Draft paragraph indices |
| PDF | Codex PDF capability, then normalize extracted text | `p.<page>:b.<block>`; lines only when extraction preserves them |
| DOCX | Codex Documents capability, then normalize extracted text | `para.<start>-para.<end>` |

Do not ask the normalizer to parse PDF or DOCX directly. Those formats require layout-aware extraction and visual verification.

## Source authority

- The uploaded or pasted screenplay is authoritative.
- Normalization may label and segment text but must not rewrite it.
- Preserve dialogue exactly, including punctuation and language.
- Keep a SHA-256 fingerprint of normalized source text, a source ID, a draft ID, format, length, extraction quality, and warnings.
- Do not expose an absolute source path in the portable result unless the user requests it; store a filename or user-provided source ID.

## Extraction quality

Use one value:

- `good`: scene order, headings, dialogue attribution, and text are reliable.
- `degraded`: useful text exists, but some layout, attribution, or references need review.
- `failed`: the source cannot support reliable scene coverage or evidence.

Typical degradation signals:

- Repeated headers/footers inside action or dialogue.
- Missing pages or paragraphs.
- OCR substitutions that change names or scene headings.
- Dialogue merged with action or assigned to the wrong speaker.
- Multi-column, dual-dialogue, revision marks, or watermarks flattened incorrectly.
- FDX paragraphs with unknown element types.

## Scene boundaries

Prefer explicit scene headings. Recognize standard English headings (`INT.`, `EXT.`, `INT./EXT.`, `I/E.`) and clear Chinese equivalents (`内景`, `外景`, `内/外`, `场景`). Preserve supplied scene numbers.

When explicit headings are absent:

- Infer a new scene only after a material location/time discontinuity.
- Mark inferred boundaries with `certainty: inferred` and a warning.
- If no defensible boundary exists, preserve the material as one scene rather than creating false precision.

## Stable IDs

Use project-local IDs:

- Scene `scn-001`
- Sequence `seq-001`
- Beat `bea-001`
- Character `chr-001`
- Location `loc-001`
- Prop `prp-001`
- Finding `fnd-001`
- Decision `dec-001`
- Role `role-<slug>` for custom roles

Never renumber an existing ID during continuation or a high-confidence draft match. New items receive the next unused number.

## Evidence and certainty

Every explicit or inferred finding must link to one or more source references, scene IDs, or beat IDs that themselves carry source references.

Use:

- `explicit`: directly present in the screenplay.
- `inferred`: conservative interpretation supported by cited evidence.
- `unknown`: required for a role or downstream decision but not supplied.

Attach `confidence: high | medium | low`. An `unknown` may have no direct source reference, but must identify the scene, role requirement, or dependency that makes the absence relevant.

## Coverage audit

Coverage must be continuous, ordered, non-overlapping, and complete for the requested scope. Record any unassigned source range. `completed` is invalid when a requested source range, scene, role, or required baseline remains pending.
