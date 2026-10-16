# Migration to v0.7

v0.7 keeps the sealed `SceneDirectionPackageV1` and the existing V1 Seedance prompt reader compatible. New compilations may use `SeedanceShotPromptRecordCollectionV2`, whose portable contract is `skills/seedance-shot-prompt-compiler/schemas/shot-prompt-records-v2.schema.json`.

V2 separates performance beats, three-layer sound design, and camera segments. Multiple camera segments may remain under one production shot ID only when every switch is bound to a real dialogue, information, action, or reaction beat. The compiler may enrich non-narrative breathing, gaze, facial tension, hand micro-actions, garment response, and matching foley; it may not change story facts, contact, core blocking, props, relationships, or shot outcomes.

The public package includes generic performance/action rules in `performance-action-realization-pack-v1`; private source texts and user review records are not distributed. Activate action-specific guidance only when the current screenplay provides relevant evidence. User-imported knowledge requires a separate review in that user's project workspace. Prompt knowledge remains isolated from prompt-free scene-direction roles.
