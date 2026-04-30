# Public Assets

This repo stores photo metadata used by the app without storing image binaries. Photo files are small JSON records that point to Unsplash image URLs and required attribution links.

## Files

- `place_photos/` mirrored place photo tree used by the app
- `place_photos/world.json` region photo metadata
- `place_photos/countries/` country, subdivision, and city photo metadata
- `manifest.json` list of place IDs with complete usable photo metadata
- `version.json` simple integer version bumped when usable photo metadata changes
- `.github/workflows/update-place-photos.yml` GitHub Actions workflow for syncing placeholders and updating cached photos
- `sync_place_photo_tree.py` mirrors missing placeholder files from the source app place tree
- `generate_place_photos.py` scans photo placeholders, fetches Unsplash metadata, rebuilds the manifest, and bumps the version when photos change
- `photo_queries.py` builds deterministic Unsplash search queries from path and `place_id` data

## Photo File Schema

Each place photo file uses a JSON array with one metadata object:

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

Blank values are valid placeholders. A photo is considered usable only when `place_id`, `image_url`, `photographer_name`, `photographer_url`, and `source_url` are all populated.

## Path and ID Conventions

Folders and filenames use dashes for readability:

```text
place_photos/countries/costa-rica/guanacaste/tamarindo.json
```

JSON `place_id` values use underscores for app consistency:

```text
city:costa_rica:guanacaste:tamarindo
```

Self files use a leading underscore so they sort before child folders and city files:

```text
place_photos/countries/costa-rica/_costa-rica.json
place_photos/countries/costa-rica/guanacaste/_guanacaste.json
```

## Manifest and Version

`manifest.json` is rebuilt from complete usable photo records only. Blank placeholders are intentionally excluded from the manifest.

`version.json` is bumped only when at least one photo metadata record is updated. Placeholder-only sync changes may be committed without bumping the version unless usable photo metadata also changed.

## Update Workflow

The workflow runs on a schedule and can also be triggered manually.

Default behavior:

- sync missing placeholder files from the source app repo
- scan blank photo records first
- query Unsplash with deterministic place queries
- update up to the configured number of successful photo records
- rebuild `manifest.json`
- bump `version.json` only when photo metadata changed
- commit only when tracked public asset files changed

The `limit` input means successful photo updates, not merely attempted candidates. No-result candidates are skipped without writing failure markers, so future runs can try them again naturally.

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
