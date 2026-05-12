# Public Assets

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and include the required photographer and source attribution links.

The repository is designed to be regenerated from a private source place tree. Generated files should stay deterministic, small, and safe to cache.

## Files

- `place_photos/` public photo metadata tree
- `place_photos/world.json` region-level photo metadata
- `place_photos/countries/` country, subdivision, and city photo metadata
- `manifest.json` list of place IDs with complete usable photo metadata
- `version.json` integer version bumped when the public photo payload changes
- `.github/workflows/update-place-photos.yml` GitHub Actions workflow for syncing, pruning, fetching, manifest rebuilding, and committing changes
- `sync_place_photo_tree.py` mirrors the current source place tree into `place_photos/countries/` and can prune stale photo files
- `generate_place_photos.py` fills missing photo metadata, rebuilds `manifest.json`, and bumps `version.json` when needed
- `photo_queries.py` builds deterministic Unsplash search queries from path and `place_id` data

## Photo File Schema

Most place photo files use a JSON array with one metadata object:

```json
[
  {
    "place_id": "city:costa_rica:guanacaste:tamarindo",
    "image_url": "",
    "photographer_name": "",
    "photographer_url": "",
    "source_url": "",
    "cached_at": ""
  }
]
```

Blank values are valid placeholders. A photo is considered usable only when all of these fields are populated:

- `place_id`
- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`

`cached_at` is stored when a photo record is written, but it is not required for manifest eligibility or stale-photo migration.

`place_photos/world.json` is the main exception to the one-object-per-file convention. It may contain multiple region-level photo records in the same JSON array.

## Path and ID Conventions

Folders and filenames use dashes for readability:

```text
place_photos/countries/costa-rica/guanacaste/tamarindo.json
```

JSON `place_id` values use underscores for app-facing consistency:

```text
city:costa_rica:guanacaste:tamarindo
```

Self files use a leading underscore so they sort before child folders and city files:

```text
place_photos/countries/costa-rica/_costa-rica.json
place_photos/countries/costa-rica/guanacaste/_guanacaste.json
```

## Manifest and Version

`manifest.json` is rebuilt from complete usable photo records only. Blank placeholders and incomplete records are intentionally excluded.

`version.json` is bumped whenever the public photo payload changes in a way clients should notice. This includes new photo metadata and manifest changes caused by stale-file cleanup.

Placeholder-only sync changes may be committed without bumping `version.json` when they do not change usable photo metadata or the manifest.

## Sync and Cleanup

`sync_place_photo_tree.py` uses the source place tree as the canonical structure for `place_photos/countries/`.

Default sync behavior:

- reads all source JSON files under the configured source countries directory
- creates missing public placeholder files
- normalizes existing public photo files to the expected schema
- preserves existing cached photo metadata when the path is still current

When run with `--prune-stale`, the script also removes public photo files that no longer exist in the source tree.

Before deleting a stale file, the script attempts a conservative photo migration:

- the stale file must contain a complete cached photo record using the same required fields as `manifest.json`
- exactly one current canonical file must match the same country and filename
- the canonical file must not already have a complete cached photo record

If those checks pass, the cached photo fields are copied into the canonical file before the stale file is deleted. `cached_at` is copied only when the stale record already has it. If the match is ambiguous or the canonical file already has a photo, the stale file is deleted without migration.

Cleanup only targets stale JSON files under `place_photos/countries/`. It does not prune `place_photos/world.json`, scripts, workflows, `manifest.json`, or `version.json` directly.

## Prune Safety Guards

Stale cleanup fails fast instead of deleting files when the source or cleanup scope looks unsafe.

The script refuses to prune when:

- the source tree produces no expected JSON files
- the public photo tree has no JSON files
- more than 10% of current public photo JSON files under `place_photos/countries/` would be deleted in one run

The 10% limit is intentionally conservative. It allows normal cleanup of small stale batches, but blocks accidental mass deletion caused by a wrong source path, broken checkout, or unexpected source tree problem.

## Update Workflow

The workflow runs on a schedule and can also be triggered manually.

Default behavior:

- check out this public assets repository
- check out the private source repository using configured secrets
- sync the current source place tree into `place_photos/countries/`
- prune stale country, subdivision, and city photo files
- migrate cached photos from stale files only when there is one safe canonical replacement
- scan blank photo records first
- query Unsplash with deterministic place queries
- update up to the configured number of successful photo records
- rebuild `manifest.json`
- bump `version.json` when photo metadata or manifest contents change
- commit only when tracked public asset files changed

The automated workflow commit message is:

```text
Update place photos
```

The `limit` input means successful photo updates, not merely attempted candidates. No-result candidates are skipped without writing failure markers, so future runs can try them again naturally.

The `overwrite` input refreshes existing cached photos instead of only filling blank placeholders.

## Unsplash Queries

Queries intentionally stay simple and avoid extra keywords.

- country: `Country`
- subdivision: `Subdivision Country`
- city primary: `City Subdivision`
- city fallback: `City Country`

Examples:

```text
Costa Rica
Guanacaste Costa Rica
Tamarindo Guanacaste
Tamarindo Costa Rica
```

## Safety Notes

Stale cleanup is based on the current source place tree. The source tree should be treated as the authority for active country, subdivision, and city paths.

The cleanup logic is intentionally conservative about migration. It only copies cached photo metadata when there is a single obvious replacement, which avoids moving photos across ambiguous place paths.

Manual deletion of stale public files should usually be unnecessary. Update the source tree first, then allow the workflow to sync, prune, rebuild the manifest, bump the version when needed, and commit the resulting public asset changes.
