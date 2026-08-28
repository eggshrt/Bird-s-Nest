# v0.4 development workflow

1. Preserve published `v0.2.0`; never rewrite history.
2. Treat v0.3 as an unpublished implementation waypoint. Do not tag or publish it.
3. Change schemas before runtime behavior. Keep old `ImagePromptPackageV1` read/export-only.
4. Run deterministic unit tests and offline E2E with Codex Python 3.12+ and the hash-locked runtime.
5. Validate all Skills, their `agents/openai.yaml`, the plugin manifest, and repository marketplace.
6. Run App Server initialization/config smoke without model usage.
7. Ask for separate usage approval before live Agent turns or GPT Image generation.
8. Update the plugin cachebuster, reinstall locally, and start a new task for discovery.
9. Commit, push `main`, and publish only tag `v0.4.0` after required non-paid checks pass.

The runtime is single-machine and process-recoverable. Cluster failover, hosted services, automatic GitHub Skill installation, external writes, and image generation remain outside v0.4.
