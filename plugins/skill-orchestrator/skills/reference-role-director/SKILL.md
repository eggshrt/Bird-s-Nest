---
name: reference-role-director
description: Assign each user-supplied reference image one permitted control dimension and explicit forbidden dimensions. Conditional dispatcher-only image-prompt role.
metadata:
  input_types: [agent_task_v1, visual_asset_requirement_v1]
  output_types: [reference_role_v1]
---

# Reference Role Director

Proceed only with a dispatcher-signed `AgentTaskV1` that includes user-supplied references. Otherwise stop and route to `$image-prompt-team`.

Hash each reference and assign it one narrow responsibility such as material behavior, silhouette logic, color relation, or camera pressure. State every dimension it must not control, record only observable traits, and check that composition plus design identity are not copied together. Do not browse, infer authorship, imitate a named living artist, or compile a prompt. Return only `AgentResultV1`; put `ReferenceRoleV1` in `claims` with `claim_type: reference_roles`.
