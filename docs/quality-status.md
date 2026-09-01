# v0.4 quality status

## Automated scope

- Offline deterministic Agent and fake App Server paths require no account, network, Codex turn, or image-generation fee.
- Tests cover V2 protocols, event replay, duplicate events, graph validation, concurrency, timeout, cancellation, retry, lease recovery, incremental DAG patching, three confirmation gates, single-asset enforcement, pure-environment boundaries, invariant visibility, old-package read-only behavior, and forbidden output fields.
- Prompt gold contains 36 sealed-contract scenarios: 16 character, 12 pure environment, and 8 hero prop.
- Every Skill and `agents/openai.yaml` is validated independently; the plugin manifest and repository marketplace are validated as a bundle.

## Capability status

- Character master: primary production target; rendered-image evaluation pending.
- Pure environment: primary production target; rendered-image evaluation pending.
- Hero prop: supported, still experimental pending more real contracts.
- Multi-view, narrative shot, state variant, failed-image repair, and image generation: deferred request types only.

## Real-project smoke status

In September 2026, one real 65-episode, 166-scene DOCX project completed the full user-facing path for a pure-environment scene state: screenplay baseline, sealed single-asset requirement, user-reference role control, all three confirmation gates, a 15-Agent-turn expert workflow with peak concurrency three, one targeted rebuttal round, prompt compilation, hash binding, and formal artifact materialization.

The user accepted the final `VisualPromptSpecV1` and Chinese master prompt. The test also exercised a high-impact direction change after an earlier approval: the final contract restored a subordinate pool, introduced neutral-cool moonlight, and replaced the live band with a structurally integrated DJ booth without leaking the superseded constraints.

This was not a clean unattended App Server pass. The first production attempt exposed a strict nested response-schema incompatibility; a second attempt was interrupted after progress. The final approved result used a dispatcher-controlled recovery DAG and passed the same single-asset, invariant-visibility, package, and spec-hash checks. Therefore real Agent execution and controlled recovery are now smoke-tested, while fully unattended schema handling and interruption recovery remain open engineering work.

No private screenplay text, user reference image, or project artifact is included in the public repository.

## Unperformed paid checks

Normal plugin execution does not generate images. GPT Image rendered-output A/B evaluation still requires separate usage authorization. The September real-project smoke validated prompt production and controlled recovery, not image-model adherence, unattended recovery, cancellation/archival across every failure mode, or long-run concurrency stability.

The render gate uses one real character and one real pure-environment contract, two images per final prompt, zero hard-boundary violations, mean contract adherence of at least 4/5, and at least 3/4 images judged first-pass usable. At least two reviewers score anonymously; a difference greater than one point adds a third reviewer.

## Local observability

Each run records scheduling latency, retries, hard timeouts, orphan-lease recovery, deadlock detection, degradation, graph versions, approvals, artifact hashes, and node attempts in the project-local event database. Audit exports are redacted. No telemetry backend is included.
