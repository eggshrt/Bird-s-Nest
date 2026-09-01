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

## Public validation boundary

The public repository reports only reproducible automated checks against synthetic fixtures and gold contracts. It intentionally excludes user screenplays, reference images, asset catalogs, concept requirements, generation prompts, run reports, and project-specific case studies. Repository `/outputs/` content is ignored by Git.

Private development runs may be used to improve the implementation, but their titles, counts, characters, scene details, design decisions, prompts, hashes, and artifacts are not part of the public quality claim.

## Unperformed paid checks

Normal plugin execution does not generate images. GPT Image rendered-output A/B evaluation requires separate usage authorization. The public release claim does not cover image-model adherence, unattended recovery across every failure mode, or long-run live concurrency stability.

The render gate uses one real character and one real pure-environment contract, two images per final prompt, zero hard-boundary violations, mean contract adherence of at least 4/5, and at least 3/4 images judged first-pass usable. At least two reviewers score anonymously; a difference greater than one point adds a third reviewer.

## Local observability

Each run records scheduling latency, retries, hard timeouts, orphan-lease recovery, deadlock detection, degradation, graph versions, approvals, artifact hashes, and node attempts in the project-local event database. Audit exports are redacted. No telemetry backend is included.
