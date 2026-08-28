# Output contract

## Destination

Default to:

```text
<workspace>/outputs/screenplay-concept-director/<project-id>/<draft-id>/
```

Generate the project catalog once per fresh baseline:

```text
asset-catalog.md
asset-catalog.json
```

After all three confirmations, write one versioned asset package:

```text
assets/<asset-id>/<version>/
├── context-snapshot.json
├── requirement.md
├── requirement.json
├── creative-position.json
└── decision-log.md
```

Never overwrite an existing version. Increment the version or stop and ask the user which existing package should be superseded.

## Commands

```bash
python3 scripts/concept_director.py catalog \
  --breakdown <breakdown.json> \
  --output <asset-catalog.json> \
  --markdown-output <asset-catalog.md>

python3 scripts/concept_director.py resolve \
  --catalog <asset-catalog.json> \
  --query '<asset name or id>'

python3 scripts/concept_director.py snapshot \
  --breakdown <breakdown.json> \
  --catalog <asset-catalog.json> \
  --asset-id <stable-id> \
  --output <context-snapshot.json>

python3 scripts/concept_director.py validate-requirement \
  --requirement <requirement.json> \
  --snapshot <context-snapshot.json> \
  --position <creative-position.json>

python3 scripts/concept_director.py materialize \
  --catalog <asset-catalog.json> \
  --snapshot <context-snapshot.json> \
  --requirement <requirement.json> \
  --position <creative-position.json> \
  --output-root <outputs/screenplay-concept-director>
```

`materialize` requires the three confirmation records and refuses an existing version directory. Its output contains concept requirements only. The V2 parent orchestrator writes `RunReportV2` in its own audit directory.
