# Extension and Custom Roles

Load this file only when an extension or custom role is selected.

## Preset extensions

### Producer — `producer`

Focus on scope, resource classes, dependencies, reuse, risk concentration, review gates, and qualitative effort. Do not output precise budgets or traditional call sheets in v1.

### Dramaturg — `dramaturg`

Focus on causality, character strategy, structure fit, genre contract, information design, dialogue purpose, setup/payoff, and the earliest upstream break. Recommend revision direction without rewriting.

### Cinematography and lighting — `cinematography_lighting`

Focus on visual point of view, framing logic, camera behavior, depth, lens tendency, exposure, contrast, color temperature, motivated sources, time/weather continuity, and reference requirements. Stop before copy-ready prompts.

### Sound and music — `sound_music`

Focus on point of audition, diegetic/off-screen information, silence, counterpoint, sync dependencies, dialogue clarity, motif, transition, atmosphere, and music function. Do not compose or generate cues unless separately requested.

### Editing — `editing`

Focus on information, emotion, action, eyeline, sound, rhythm, continuity, ellipsis, compression/expansion, parallel action, reaction priority, and transition logic.

### VFX and compositing — `vfx`

Focus on effects moments, asset dependencies, interaction surfaces, masks/plates/passes, screens/reflections, environment integration, complexity, continuity, acceptance checks, and fallback. Remain provider-neutral.

### Continuity — `continuity`

Focus on chronology, geography, entry/exit state, knowledge, relationships, costume, hair, injury, dirt/wetness, props, hands, screen direction, weather, light, damage, and unresolved discontinuities.

## Custom role contract

When a user names an unknown or project-specific role:

1. Infer a draft contract from the role name and project context.
2. Present it for confirmation before analysis.
3. Resolve overlap with built-in roles explicitly.
4. Preserve the confirmed contract in `role_reports[].contract`.

Contract fields:

```json
{
  "role_id": "role-example",
  "display_name": "岗位名称",
  "objective": "The decision this role owns",
  "questions": ["Questions this role must answer"],
  "deliverables": ["Artifacts or decisions it returns"],
  "dependencies": ["Required upstream inputs"],
  "exclusions": ["Decisions owned elsewhere"],
  "confirmed": true
}
```

Do not treat a title alone as confirmation. If the contract conflicts with another role, include the authority boundary in cross-role decisions.

