# v0.4 workflow

```text
sealed requirement + confirmed presentation
                 │
        evidence guardian
                 │
    asset specialist + six independent positions
                 │
        visual spec assembler
             ┌───┴───┐
   production review  adversarial review
             └───┬───┘
        evidence adjudication
                 │
        gate 2: spec confirmation
                 │
        salience editor → OpenAI compiler
                 │
        gate 3: final confirmation → files
```

All six creative roles execute on every run. The matching asset specialist also executes; `reference-role-director` runs only when the user supplied references. Conflicts are resolved by evidence authority, not voting. A real conflict may trigger at most one targeted rebuttal round, recorded in the spec.

Idempotent nodes retry once. Each run allows one automatic affected-subgraph replan. App Server or scheduler interruption resumes from events and thread IDs. A pre-v0.4 run is read/export-only. Full execution mode is required; degraded output cannot be silently promoted.

Changed wording, framing, or adapter behavior may invalidate only downstream nodes if all invariants remain visible. Changed asset identity, design direction, or core acceptance freezes the run and returns to concept direction.
