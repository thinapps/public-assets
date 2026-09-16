# Public Assets

This repository stores public photo metadata without storing image binaries. Photo records reference external image URLs and preserve required photographer and source attribution links.

Country, subdivision, and city photo paths are generated from a private source place tree. Region records in `place_photos/world.json` are maintained separately.

## Public data

- `place_photos/` canonical per-place photo metadata tree
- `manifest.json` place IDs with complete usable photo metadata
- `photos.json` generated bulk photo lookup keyed by place ID
- `version.json` integer version for public payload changes

`photo_cursor.json` is operational workflow state and is not part of the public data payload.

## Documentation

Detailed documentation covers the public photo data model, selection workflow, synchronization and cleanup behavior, workflow operations, and Unsplash API compliance requirements.

| Document | Description |
| --- | --- |
| [Agents](agents.md) | Defines persistent repository instructions for AI agents and coding assistants, including required reading, data and workflow guardrails, Unsplash requirements, Git policy, and change-review expectations. |
| [Photo Data](docs/photo-data.md) | Defines the public photo-data schema, directory structure, placeholders, manifest and version behavior, attribution fields, and generated-data maintenance policy. |
| [Photo Selection](docs/photo-selection.md) | Explains candidate ordering, attempt limits, cursor progress, Unsplash search queries, photo selection rules, and handling for no-result, rate-limit, and failure cases. |
| [Sync and Cleanup](docs/sync-and-cleanup.md) | Covers synchronization from the source place tree, cached-photo migration, stale-path pruning, cleanup behavior, and safeguards that prevent accidental data loss. |
| [GitHub Actions](docs/github-actions.md) | Documents workflow scheduling and manual inputs, secrets, concurrency, reliability design, timeout and failure behavior, result summaries, and operational details. |
| [Unsplash Compliance](docs/unsplash-compliance.md) | Records the Unsplash API compliance model, including hotlinking, attribution and referral parameters, API-key handling, download-location tracking, scheduled workflow rationale, and maintenance checks. |
