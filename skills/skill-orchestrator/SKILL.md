---
name: skill-orchestrator
description: Explicit-only V2 controller with three entry tiers. Light gives unsealed single-role advice from an existing alignment record; Standard runs a scoped multi-role council with a short record; Formal aligns the requirement, retrieves Skills through the capability registry, proposes a typed DAG, and drives a recoverable multi-Agent run with event-sourced audit and evidence-backed validation. Use only when the user explicitly invokes $skill-orchestrator.
metadata:
  input_types: [spoken_requirement, visual_asset_requirement_v1]
  output_types: [requirement_contract_v2, execution_graph_v2, run_report_v2]
---

# Skill Orchestrator V2

This Skill is the semantic controller. It defines goals and typed tasks; `scripts/orchestrator_runtime.py` is the deterministic scheduler. Never let an LLM mutate scheduler state or silently repair a DAG.

## Entry and tiers

Require explicit `$skill-orchestrator` invocation. One invocation covers follow-ups of the same task; a user-written project instruction file that records a standing invocation counts for that project until the user revokes it. Never treat such a record as execution confirmation, a completed council, or a seal.

Pick a tier by the first matching rule, state it in one sentence with the signal that decided it, and proceed. The user may change it.

**进度通知格式**（每档均适用）：档位选定后，第一条消息说明任务概要、涉及岗位/步骤数量和预计时间，例如"好的，我来帮你[用一句话描述任务]。这需要[N个岗位/步骤]，大概[X分钟]。"每个步骤开始时告知"正在[做什么]…"，完成时告知"[这步的产出]已完成。"遇到需用户确认的问题时，说明具体情况并问一个明确问题。用户侧可见输出中禁止出现：council_cNNN、record_id、schema_version、native_agent、inline、executor、node_001等节点ID、run_rNNN、RunReportV2、AgentResultV1、AgentTaskV1、任何十六进制哈希值、"此任务需依据知识库"等内部标注。

1. **Formal** if any holds: the request says 封存/正式/交付包/导演包/提示词包/seal; the target is a sealed type (`visual_asset_requirement_v1`, `scene_direction_package_v1`, `image_prompt_package_v2`), a DOCX/XLSX, or a compiler input; any side effect is involved; a sealed artifact would change.
2. **Standard** if two or more roles must give independent positions, or a real cross-role conflict needs adjudication.
3. **Light** if all hold: one role Skill; no side effect beyond an optional marked draft; an existing alignment record is readable, or the user-supplied material is self-contained.
4. Otherwise Standard.

Escalate automatically and say so: Light to Standard when a second role is needed or the alignment record is missing, stale, or self-contradictory; any tier to Formal when a Formal signal appears. De-escalate only on the user's explicit instruction, never mid-run in Formal, and never into a tier whose conditions fail.

Light is never allowed for: a sealing or formal request; any side effect; no alignment record and no self-contained material; a multi-role council; image-team internal roles, which accept only dispatcher-signed tasks; the shot-prose and Seedance compilers.

## Light

Read the alignment record and later user decisions, load the one role Skill body, and answer in the controller thread. Do not load `$grill-me`, re-interview, rebuild the index, show a graph, create a run, or start an Agent. Ask only about new facts that change this answer, at most three.

- Open the reply with one line: tier, role Skill, alignment record read.
- 在开头用括号标注「草稿建议，未正式封存」. Separate user-confirmed facts, observations, and unconfirmed inference. List changes to dialogue, plot, relationships, physical contact, or core blocking as proposals for the user.
- Save only on request, as a new draft version recording: tier, role Skill and version, alignment record path and hash, date, proposed status, not sealed. Never overwrite a source or confirmed version, and never name the file a package.
- Never call the result a council, a multi-role consultation, or a package.

## Standard

Confirm scope in one short exchange (shots, question, roles, what is out of scope), reusing settled project context. Start one Agent per selected role, at most three in parallel, each with a task-bounded context projection and a private output file; roles do not interview the user. One targeted rebuttal per real conflict; no voting. The controller synthesizes and labels the result 「多岗位会诊草稿，未正式封存」.

在工作目录里保存一份会诊记录，包含：档位、创建时间、范围（含用户确认原文）、对齐输入（路径与哈希）、各岗位信息（岗位技能与版本、执行方式、代理标识、产出路径与哈希）、综合结论（路径与哈希）、用户确认状态、建议内容、未决冲突、未完成项、状态标记为草稿且未封存。一个由控制器自身执行的岗位记录为内部执行，不作为独立代理。用户侧可见输出中不出现内部字段名、目录名或节点标识。

Light and Standard never produce a formal sealed run report, a canonical package hash, an approval marker, a dispatcher signature, or a numbered run directory. Promotion to Formal starts at gate 1; lower-tier output enters only as added context.

## Formal: hard gates

1. Require explicit `$skill-orchestrator` invocation.
2. Load sibling `$grill-me`, inspect discoverable facts, close the design tree, and confirm shared understanding.
3. Create `RequirementContractV2` and one versioned `CollaborationContextV1`.
4. Refresh the local Skill index, retrieve against the normalized contract, read qualified Skill bodies, and propose `ExecutionGraphV2`.
5. Show goal, selected Skills, evidence, Agent count, peak concurrency, permissions, side effects, DAG, and verification. Obtain execution confirmation.
6. Only then create a run in the V2 event store and execute it.

Everything from here on applies in full to Formal. No tier relaxes it.

Danger mode is a host prerequisite, not business authorization. Never modify Codex configuration. Publishing, payment, destructive work, credentials, image generation, and new external writes still need explicit node-local authorization; the v0.4 runtime rejects these side effects by default.

## Four-quadrant context

Maintain one canonical collaboration context with `shared_known`, `user_context_gaps`, `agent_added_context`, and `joint_unknown_hypotheses`. Every entry records provenance, confidence, impact, status, and verification. Agents receive task-bounded projections and return discoveries as `AgentResultV1`; they do not interview the user. Deduplicate blocking questions and ask at most three per round, with no round limit.

**Knowledge base mandatory loading rule**:
- When the requirement is identified as asset design (character styling, scene, prop), **must** include the corresponding asset plugin's `knowledge/` directory content in context projection
- Agent receives its task file **must** explicitly mark the knowledge-base requirement internally; this marking is not shown to the user
- Output **must** include knowledge base citation tracking

## Retrieval

Run the hash-locked bootstrap only with Codex-bundled Python 3.12+. Preserve scan precedence:

1. project `.codex/skills`
2. project `.agents/skills`
3. user `.codex/skills`
4. user `.agents/skills`
5. plugin cache

Within the plugin cache, index only the highest cached version of each plugin and only the `skills` path its manifest declares; superseded versions and plugins vendored inside another plugin are not indexed. The catalog lists the chosen versions under `plugins`. The first same-name definition wins and lower-priority copies remain `shadowed`.

The index merges capability registries (`CapabilityRegistryV1`, see [interfaces.md](references/interfaces.md)): the bundled `references/capability-registry.json`, then `$CODEX_HOME/skill-orchestrator/capability-registry.json`, then `<project>/.codex/skill-orchestrator/capability-registry.json`; later files win per Skill. An entry gives a Skill its domain pack (`screenplay_intake`, `asset_design`, `directing`, `prompt_compile`, `delivery`, `meta`, `utility`), input/output types, and `entry_only`. Entry Skills answer for their domain; `entry_only` roles are loaded only by their entry Skill, by this controller in Light or Standard, or by a dispatcher-signed task. A registry can widen permissions and raise risk, never lower them, and an entry pinned to a plugin version or content hash stops applying when the Skill changes; treat `registry.problems` in the catalog as unregistered Skills. Light and Standard resolve roles with `orchestrator_index.py domains --catalog <catalog>` on the existing catalog.

Retrieve up to 12 lexical candidates, apply input/output, risk, permission, and exclusion filters, then read candidate bodies and rerank to at most five with a Top 3. Dynamic experts require local presence, at least 0.8 confidence, compatible input, and no network/external-write permission; choose at most two and choose none when no candidate qualifies. Select them with `search --dynamic-expert`, which enforces the confidence floor, denies network, external-write, and media-generation permissions, caps risk at medium, and excludes `entry_only` roles. A Skill that fails this gate can still run as an explicitly confirmed node through its domain entry.

Use [github-fallback.md](references/github-fallback.md) only when local retrieval has no qualified candidate. Never auto-install or run an unreviewed external script.

## DAG and scheduling

Every node declares a unique ID, role Skill, objective, input bindings, output schema, dependencies, execution mode, idempotency, soft/hard timeout, permissions, side effects, risk, and verification.

- Reject cycles, missing bindings, duplicate objectives, forbidden effects, and concurrency above three.
- The scheduler may detect a problem but never silently change task semantics. The controller proposes `DagPatchV1`; high-impact patches need reconfirmation.
- A goal-preserving addition may update the current graph. A changed goal, asset, requirement hash, or core acceptance criterion freezes the run and derives a new one.
- Changed upstream inputs invalidate every affected descendant.
- Idempotent nodes retry once. Non-idempotent nodes do not auto-retry. One automatic affected-subgraph replan is allowed per run.
- Read-only work may fall back to single-Agent serial execution only as `degraded`, requiring explicit acceptance.

Use the adaptive cap `min(3, host slots, ready nodes, actual experts)`. Keep shared project facts read-only and give every node a private writable directory with declared artifact bindings.

## State and recovery

The project SQLite database uses an append-only `RunEventV1` log as truth. Run/node/approval/artifact/metric tables are disposable projections. The runtime CLI provides `status`, `cancel`, `replay`, `export`, `prune`, and `validate-graph`; cancellation is cooperative for 30 seconds before forced interruption. Default node soft/hard timeouts are 300/600 seconds, with a 20-second heartbeat and 60-second lease.

The Codex App Server bridge starts, resumes, interrupts, and archives Agent threads. Persist thread IDs. Promise process-level local recovery only, never cluster HA.

When host-native collaboration Agents are the workers, drive the run with the bundled `scripts/native_bridge.py`; never hand-write or copy a bridge into a run directory. The run directory holds only `requirement.json`, `graph.json`, and `nodes/<node_id>/`. Each bridge step is a short command printing one JSON object: `init` validates the contract, graph, and authoritative-input hash; `approve` records the user's own confirming words and refuses without them; `claim` leases ready nodes and writes signed, binding-projected `task.json` files; `submit` validates the result, task ID, signature, worker identity, artifact hashes, and private-directory boundary; `expire` retries an overdue idempotent node once; `answer` resumes after blocking questions; `finalize` writes the snapshot, audit, and `run_report.json`; `accept` records the user's final acceptance. Leases use wall-clock deadlines, and a result that arrives after its deadline is recorded only through the explicit, audited `submit --accept-late`. `claim --single-agent`, or a multi-node run completed only by the controller, ends as `degraded_pending_acceptance`.

## Bundled verticals

- `$ai-script-breakdown` produces `screenplay_breakdown_v1`.
- `$screenplay-concept-director` consumes the baseline and produces a sealed `visual_asset_requirement_v1` without prompt fields.
- `$image-prompt-team` exclusively consumes that sealed requirement, pauses for `visual_prompt_spec_v1` confirmation, and then produces `image_prompt_package_v2` plus `run_report_v2`.

The specialized domain validators remain authoritative. The generic controller must not weaken their evidence, freshness, single-asset, confirmation, or no-image boundaries.

## References and scripts

- [interfaces.md](references/interfaces.md): V2 contracts, states, patch rules, semantic registrations, `CapabilityRegistryV1`, and the non-sealable `advisory_note_v1` and `council_record_v1`.
- `references/capability-registry.json`: bundled registry for the Skills shipped with this plugin.
- [github-fallback.md](references/github-fallback.md): reviewed, pinned GitHub candidate flow.
- `scripts/orchestrator_index.py`: index, capability registries, domain lookup, retrieval, V2 graph validation, and external Skill audit.
- `scripts/orchestrator_runtime.py`: event store, scheduler, App Server bridge, recovery, export, and pruning.
- `scripts/native_bridge.py`: official file bridge between the event store and host-native collaboration workers. Formal only; standard library only; loads the runtime from its own plugin version.
- `scripts/bootstrap_runtime.py`: Python 3.12 hash-locked dependency bootstrap.

## 可复用光照与材质增强（本地0.8.1）

新增`$dlss5-lighting-director`用于用户明确的光影/材质增强，也由已有`color-light-director`与`scene-dengguang-daoyan`按需加载。它转译保留基础、定向增强和范围保护的思路，不调用NVIDIA SDK或模型，不生成图片/视频。默认在当前岗位内使用共享方法，不按子问题新增Agent或重新启动全导演组。图片团队与封存导演链的既有门槛、返回合同和各岗位设计权不变；用户直接给已有提示词只改光影时可用该独立Skill，不伪造单资产封存包。

入口与方法见[DLSS 5式光照与材质增强](../dlss5-lighting-director/SKILL.md)。本次只做本地试用，用户明确要求暂不测试，不把安装或文件核对称为效果通过。
