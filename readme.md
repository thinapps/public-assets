# Public Assets

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and preserve the required photographer and source attribution links.

The data is generated from a private source place tree. Generated output should remain deterministic, compact, and safe for clients to cache.

## Public data

- `place_photos/` public photo metadata tree
- `place_photos/world.json` region-level photo metadata
- `place_photos/countries/` country, subdivision, and city photo metadata
- `manifest.json` place IDs with complete usable photo metadata
- `version.json` integer public payload version

Most place files contain one photo metadata object inside a JSON array. Blank values are valid placeholders and are excluded from `manifest.json` until all required photo and attribution fields are populated.

Folders and filenames use lowercase dashes. JSON `place_id` values use lowercase underscores and colon-separated place levels.

See [`docs/photo-data.md`](docs/photo-data.md) for the complete schema, path conventions, manifest rules, version behavior, and generated data policy.

## Automation

The scheduled GitHub Actions workflow:

1. checks out this repository and the private source repository
2. synchronizes the current source place tree into `place_photos/countries/`
3. safely migrates eligible cached photos and prunes stale files
4. attempts Unsplash searches for missing photo metadata
5. rebuilds `manifest.json`
6. bumps `version.json` when public photo data or the manifest changes
7. commits only when tracked public assets changed

The default run attempts up to 10 eligible place entries. The limit counts attempted entries, not successful matches. No eligible entries, no search results, rate-limit exhaustion, and no repository changes are normal successful outcomes.

See [`docs/github-actions.md`](docs/github-actions.md) for workflow inputs, required secrets, graceful outcomes, real failures, and timeout behavior.

## Sync and cleanup

The private source place tree is the authority for active country, subdivision, and city paths.

`sync_place_photo_tree.py` creates and normalizes public placeholders. With `--prune-stale`, it removes files that no longer exist in the source tree after applying conservative cached-photo migration rules.

Cleanup refuses to proceed when the source scope is empty, the public photo tree is empty, or more than 10% of current public country photo files would be deleted in one run.

See [`docs/sync-and-cleanup.md`](docs/sync-and-cleanup.md) for synchronization behavior, migration requirements, deletion safeguards, and manual maintenance policy.

## Repository files

- `.github/workflows/update-place-photos.yml` runs the scheduled and manual update workflow
- `sync_place_photo_tree.py` synchronizes placeholders and safely prunes stale files
- `generate_place_photos.py` selects candidates, searches Unsplash, writes photo records, rebuilds the manifest, and updates the version
- `photo_queries.py` builds deterministic search queries from place IDs and paths
- `docs/github-actions.md` documents workflow operation and failure policy
- `docs/photo-data.md` documents the public data contract
- `docs/sync-and-cleanup.md` documents synchronization and stale cleanup

## Generated data policy

Files under `place_photos/countries/`, along with `manifest.json` and `version.json`, are managed by the scripts and workflow.

Normal place additions, removals, renames, and path changes should be made in the private source place tree first. Manual edits to generated public files should be limited to deliberate repairs.