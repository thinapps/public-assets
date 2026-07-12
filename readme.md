# Public Assets

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and preserve required photographer and source attribution links.

Country, subdivision, and city photo paths are generated from a private source place tree. Region records in `place_photos/world.json` are maintained separately.

## Public data

- `place_photos/` photo metadata tree
- `manifest.json` place IDs with complete usable photo metadata
- `version.json` public payload version

## Automation

The scheduled and manual workflow synchronizes country, subdivision, and city photo paths, searches Unsplash for eligible photo entries, rebuilds the manifest, updates the version when required, and commits resulting public asset changes.

## Documentation

- [`docs/photo-data.md`](docs/photo-data.md): Schema, paths, placeholders, manifest, versioning, attribution, and generated-data policy.
- [`docs/photo-selection.md`](docs/photo-selection.md): Candidate ordering, queries, Unsplash settings, selection, retries, and rate-limit behavior.
- [`docs/sync-and-cleanup.md`](docs/sync-and-cleanup.md): Source synchronization, cached-photo migration, pruning, and deletion safeguards.
- [`docs/github-actions.md`](docs/github-actions.md): Schedule, inputs, secrets, concurrency, failures, timeout, and workflow operation.
