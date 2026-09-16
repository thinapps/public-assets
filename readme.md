# Public Assets

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and preserve required photographer and source attribution links.

Country, subdivision, and city photo paths are generated from a private source place tree. Region records in `place_photos/world.json` are maintained separately.

## Public data

- `place_photos/` photo metadata tree
- `manifest.json` place IDs with complete usable photo metadata
- `version.json` public payload version

## Automation

The scheduled and manual workflow synchronizes country, subdivision, and city photo paths, searches Unsplash for eligible photo entries, rebuilds the manifest, updates the version when public photo data changes, and commits resulting updates.

Normal scheduled runs use a bounded attempt count and resume through the blank-entry queue with `photo_cursor.json`. This keeps run time predictable, avoids repeatedly blocking on the same no-result entries, and allows cursor-only progress without an unnecessary public version bump.

## Documentation

Detailed documentation covers the public photo data model, selection workflow, synchronization and cleanup behavior, automation, and Unsplash API compliance requirements.

| Document | Description |
| --- | --- |
| [`docs/photo-data.md`](docs/photo-data.md) | Defines the public photo-data schema, directory structure, placeholders, manifest and version behavior, attribution fields, and generated-data maintenance policy. |
| [`docs/photo-selection.md`](docs/photo-selection.md) | Explains candidate ordering, attempt limits, cursor progress, Unsplash search queries, photo selection rules, and handling for no-result, rate-limit, and failure cases. |
| [`docs/sync-and-cleanup.md`](docs/sync-and-cleanup.md) | Covers synchronization from the source place tree, cached-photo migration, stale-path pruning, cleanup behavior, and safeguards that prevent accidental data loss. |
| [`docs/github-actions.md`](docs/github-actions.md) | Documents workflow scheduling and manual inputs, secrets, concurrency, reliability design, timeout and failure behavior, result summaries, and operational details. |
| [`docs/unsplash-compliance.md`](docs/unsplash-compliance.md) | Records the Unsplash API compliance model, including hotlinking, attribution and referral parameters, API-key handling, download-location tracking, automation rationale, and maintenance checks. |
