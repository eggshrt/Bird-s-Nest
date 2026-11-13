# Art and Storyboard Roles

Load only when `art` or `storyboard` is selected.

## Art — `art`

### Objective

Build a coherent, reusable, photoreal visual world whose asset states serve story, character, and AI continuity.

### Dimensions

- World era, geography, culture, social hierarchy, physical rules, realism, and visual exclusions.
- Location function, emotional property, geography, movement paths, lighting sources, weather, damage, and reusable coverage.
- Character identity, silhouette, age, body, face, hair, costume states, wear, injury, and arc-linked changes.
- Prop identity, material, scale, ownership, state change, interaction, and payoff.
- Color, contrast, texture, material, light, atmosphere, and recurring motif systems.
- Asset reuse, state variants, reference coverage, and generatability.

### Deliverables

- World and style rules.
- Character, location, costume, prop, and effect asset registers with stable IDs.
- Required states and variation matrix across scenes.
- Color/light/material progression tied to story evidence.
- Location geography and continuity constraints.
- Missing reference assets, reuse opportunities, and high-risk designs.

Do not optimize only for appearance. Every major art decision must support story function, character, spatial clarity, continuity, or production feasibility.

## Storyboard — `storyboard`

### Objective

Translate approved beats and role constraints into an executable shot blueprint while preserving spatial, performance, editorial, and AI-generation continuity.

### Shot blueprint fields

- Stable shot ID and source scene/beat IDs.
- Dramatic purpose and audience information change.
- Subject, action, reaction, and performance target.
- Framing, angle, camera position, lens tendency, and movement.
- Blocking, screen direction, axis, eyeline, foreground/midground/background, and geography.
- Estimated duration or `unknown`, plus timing dependency.
- First-frame state, last-frame state, and handoff to adjacent shots.
- Dialogue, sound, edit, transition, asset, and continuity dependencies.
- AI complexity, required references, fallback, and acceptance check.

### Rules

- Create a new shot only when image, information, attention, space, time, performance, or rhythm needs a cut or camera-state change.
- Preserve every required dramatic beat; do not create decorative coverage.
- Treat axis, eyeline, body direction, prop handoff, light, weather, costume, and damage as explicit continuity state.
- Use `unknown` for unsupported duration, lens, or movement choices and make a proposal only when the director decision logically supports it.
- Do not include `prompt`, `generation_prompt`, `negative_prompt`, provider syntax, or copy-ready generation prose.

### Deliverables

- Shot blueprint grouped by scene and beat.
- Spatial baseline and axis/eyeline rules.
- First/last-frame continuity ledger.
- Transition, sound, edit, and asset dependency list.
- Coverage gaps, risky shots, and platform-neutral fallback options.

