# GitHub fallback protocol

Run this protocol only after local retrieval has no qualified candidate.

## Discovery

Search GitHub for repositories that contain an Agent Skills-compatible `SKILL.md`. Prefer exact capability matches, a clear license, recent maintenance, tagged releases, tests, and minimal executable surface.

For every candidate present:

- repository and exact commit SHA;
- license and any missing or ambiguous licensing;
- last meaningful maintenance activity;
- the complete candidate `SKILL.md` for review;
- every bundled file, with scripts called out;
- required tools, network access, credentials, permissions, and external side effects;
- security audit findings and file checksums.

Do not treat stars as a security signal or capability proof.

## Review

Download candidate content to a temporary directory without executing hooks or scripts. Run:

```bash
python orchestrator_index.py audit-skill --path /temporary/candidate
```

Reject path traversal, symlinks escaping the candidate root, hidden payloads, undocumented binaries, unexpected executables, or scripts whose behavior cannot be explained. Inspect every network endpoint, subprocess, file write, destructive command, and credential reference. Unreviewed executable content is ineligible.

## Approval and installation

Show the review and ask for explicit installation approval. Approval must identify the repository, skill, destination, and commit SHA. Discovery approval is not installation approval.

After approval, install the reviewed tree directly to `~/.agents/skills/<skill-name>/` at the pinned commit. Do not use a moving branch or tag. Preserve a receipt containing the source URL, commit SHA, file hashes, license, review time, and reviewer decision. Then rebuild the local index and regenerate the DAG.

Never auto-install. Never auto-upgrade. Never execute an external script merely to determine what it does.
