# Stable interfaces

All interfaces use `schema_version` exactly as shown. Unknown additive fields are allowed; required fields may not be omitted.

Machine-readable schemas live in `references/schemas/`. Run `scripts/orchestrator_index.py validate-interface` for semantic checks that JSON Schema alone cannot express, including DAG cycles, bindings, English retrieval terms, and the global retry cap.

## RequirementContractV1

```json
{
  "schema_version": "RequirementContractV1",
  "goal": "Observable desired outcome",
  "audience": ["Who consumes the result"],
  "inputs": [{"name": "source", "type": "document", "location": "user-provided"}],
  "deliverables": [{"name": "report", "type": "markdown", "required": true}],
  "in_scope": ["Included work"],
  "out_of_scope": ["Excluded work"],
  "constraints": ["Time, tooling, policy, format, or quality constraint"],
  "assumptions": [{"statement": "Assumption", "validation": "How it will be checked"}],
  "acceptance_criteria": [{"id": "AC-1", "criterion": "Observable pass condition", "method": "Verification method"}],
  "open_questions": [],
  "retrieval_query": "English capability-oriented query",
  "retrieval_terms": ["English", "search", "terms"],
  "confirmed_at": "ISO-8601 timestamp"
}
```

`open_questions` must be empty before the first confirmation. Inputs and deliverables use semantic types so compatible skill outputs can be bound to later inputs.

## ExecutionPlanV1

```json
{
  "schema_version": "ExecutionPlanV1",
  "requirement_contract_ref": "requirement.json",
  "parallel_authorized": false,
  "retry_policy": {"max_replans": 1},
  "nodes": [
    {
      "id": "N1",
      "skill": {"name": "example-skill", "path": "/absolute/path/SKILL.md", "content_hash": "sha256"},
      "goal": "Node-local outcome",
      "input_bindings": [{"input": "source", "from": "requirement.inputs.source"}],
      "expected_outputs": [{"name": "result", "type": "markdown"}],
      "depends_on": [],
      "execution_mode": "serial",
      "permissions": ["filesystem:read"],
      "side_effects": [],
      "risk": "low",
      "confirmation_required": false,
      "verification": {"method": "Inspect generated file", "evidence": "Path and checks"}
    }
  ],
  "confirmed_at": null
}
```

`depends_on` forms a DAG. `from` may reference `requirement.*` or an earlier node as `<node-id>.outputs.<name>`. `execution_mode` is `serial` unless `parallel_authorized` is true and the node is independent. Risks are `low`, `medium`, `high`, or `critical`.

## RunReportV1

```json
{
  "schema_version": "RunReportV1",
  "plan_ref": "plan.json",
  "started_at": "ISO-8601 timestamp",
  "completed_at": "ISO-8601 timestamp",
  "nodes": [
    {
      "id": "N1",
      "status": "succeeded",
      "artifacts": [{"name": "result", "type": "markdown", "location": "/absolute/path"}],
      "validation_evidence": [{"criterion": "AC-1", "result": "pass", "evidence": "Observed fact"}],
      "errors": [],
      "attempts": 1
    }
  ],
  "replans_used": 0,
  "final_status": "succeeded",
  "conclusion": "Concise evidence-backed conclusion"
}
```

Node status is one of `pending`, `running`, `succeeded`, `failed`, `blocked`, or `skipped`. `replans_used` must be 0 or 1.
