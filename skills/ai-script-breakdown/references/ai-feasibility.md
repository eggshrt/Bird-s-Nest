# Provider-neutral AI Feasibility Baseline

Run this baseline for every approved scene and beat. It tests whether animation-style preproduction has locked enough information to generate coherent photoreal live action. It does not choose a provider, write prompts, or create a shot list.

## 1. Asset registry and lock state

Track stable IDs and coverage for:

- Characters: identity, apparent age, body, face, hair, wardrobe states, injuries, carried objects, and voice/lip-sync identity.
- Locations: architecture, geography, entry/exit points, scale, lighting sources, weather, time state, and reusable views.
- Props and vehicles: appearance, size, material, ownership, state changes, hand contact, and story function.
- Effects: practical-looking phenomena, environment interaction, transformations, crowds, creatures, destruction, screens, and typography.

Use `locked`, `partial`, or `missing`. A screenplay mention is not automatically a locked design.

## 2. Continuity state

For each scene or beat record the required start and end state for:

- Character identity, costume, hair, makeup, injury, dirt, wetness, age, and emotion visibility.
- Position, facing, eyeline, hand occupancy, body action, and screen direction.
- Location geometry, time, weather, lighting, damage, crowd, and prop placement.
- Knowledge, relationship power, and narrative state when these affect visible performance.

Flag any state that cannot be reconstructed from the source or approved design assets.

## 3. Generation complexity

Tag only what the evidence requires:

- `multi_character_interaction`
- `fine_hand_object_contact`
- `lip_sync_or_dense_dialogue`
- `identity_sensitive_closeup`
- `complex_body_motion`
- `crowd_or_many_agents`
- `camera_subject_coordination`
- `long_continuous_action`
- `reflection_transparency_or_screen`
- `weather_water_fire_smoke`
- `transformation_or_destruction`
- `continuity_sensitive_match`

Rate scene/beat complexity `low`, `medium`, `high`, or `blocker`, and explain the driver. Do not infer that a named provider can or cannot perform it.

## 4. Reference strategy requirements

Identify required references without generating them:

- Character identity and wardrobe states.
- Location master, geography, and key angles.
- Hero props and hand-scale reference.
- Performance pose or motion reference.
- Start frame, end frame, or transition handoff state.
- Shared look, lens behavior, lighting logic, grain/texture, and aspect ratio.

Distinguish `required_before_generation`, `helpful`, and `not_needed`.

## 5. Duration and segmentation pressure

- Estimate only when the screenplay supports timing; otherwise use `unknown`.
- Flag beats whose dialogue, action, or state change is too dense for a single reliable generation unit.
- Recommend a semantic split at an action/reaction or state boundary, never at an arbitrary duration.
- Without the storyboard role, describe segmentation pressure but do not invent shots.

## 6. Sound and lip-sync dependencies

Track dialogue speaker, off-screen speech, narration, breaths, exertion, music dependency, sound-led transitions, and sync-critical effects. Identify whether picture timing depends on locked dialogue or sound. Do not generate voice profiles or music prompts.

## 7. Risk and fallback

For each high-risk item, provide:

- Evidence and affected scene/beat IDs.
- Required upstream lock or test.
- A platform-neutral fallback such as simplifying simultaneous action, separating interaction into clean state changes, using a cutaway, changing visible contact, shortening a continuous move, or allocating a composite/VFX pass.
- What story, performance, or visual value the fallback must preserve.

Never recommend removing a story-critical action solely because it is difficult. Escalate the tradeoff to the relevant role.

## Baseline output

Populate `ai_feasibility` with:

- `asset_locks`
- `continuity_requirements`
- `complexity_flags`
- `reference_requirements`
- `duration_pressure`
- `audio_dependencies`
- `risks`
- `fallbacks`
- `blockers`

