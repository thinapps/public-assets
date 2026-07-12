# Photo Data

## Purpose

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and include photographer and source attribution links.

Country, subdivision, and city photo paths are generated from a private source place tree. Region records in `place_photos/world.json` are maintained separately. Generated structure and ordering should remain deterministic, compact, and safe for clients to cache.

## Public files

- `place_photos/` contains the public photo metadata tree.
- `place_photos/world.json` contains region-level photo records.
- `place_photos/countries/` contains country, subdivision, and city photo records.
- `manifest.json` lists place IDs with complete usable photo metadata.
- `version.json` contains the integer public payload version.

## Photo file schema

Most place photo files contain a JSON array with one metadata object:

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

An entry with an empty `image_url` is a valid placeholder and remains eligible for future photo searches. Records missing other required fields are incomplete and excluded from `manifest.json`.

A photo is complete and usable only when all of these fields contain non-empty strings:

- `place_id`
- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`

`cached_at` records when the cached photo metadata was written. It is optional for manifest eligibility and stale-photo migration.

`place_photos/world.json` is the main exception to the one-object-per-file convention. It may contain multiple region-level records in one JSON array.

## Path conventions

Folders and filenames use lowercase dashes for readability:

```text
place_photos/countries/costa-rica/guanacaste/tamarindo.json
```

Country and subdivision self files use a leading underscore so they sort before child folders and city files:

```text
place_photos/countries/costa-rica/_costa-rica.json
place_photos/countries/costa-rica/guanacaste/_guanacaste.json
```

Normal path shapes are:

```text
place_photos/world.json
place_photos/countries/{country}/_{country}.json
place_photos/countries/{country}/{subdivision}/_{subdivision}.json
place_photos/countries/{country}/{subdivision}/{city}.json
```

## Place ID conventions

JSON `place_id` values use lowercase underscores and colon-separated place levels:

```text
region:central_america
country:costa_rica
subdivision:costa_rica:guanacaste
city:costa_rica:guanacaste:tamarindo
```

Paths use dashes while place IDs use underscores. The scripts convert between these forms when inferring IDs or search labels.

When a stored `place_id` conflicts with a normal country, subdivision, or city file path, photo query generation treats the path as the safer fallback source of truth. `world.json` is a shared exception: its region records use their stored `region:*` IDs because the file path cannot identify an individual region.

## Manifest

`manifest.json` is rebuilt from complete usable photo records only.

It intentionally excludes:

- blank placeholders
- incomplete photo records
- files with invalid non-list payloads

The manifest contains unique place IDs in deterministic sorted order.

Clients can use the manifest to determine whether usable cached photo metadata exists before requesting a place file.

## Version

`version.json` is bumped when generated public output changes in a way clients should notice. This includes:

- newly cached photo metadata
- refreshed photo metadata in overwrite mode
- manifest changes caused by place additions, removals, or stale-file cleanup

Placeholder-only synchronization may be committed without a version bump when it does not change usable photo metadata or the manifest.

No version bump occurs when a run attempts searches but produces no public data changes.

## Photo attribution

Each usable photo record preserves:

- the external image URL
- the photographer name
- a photographer profile URL
- the original photo source URL

Photographer and source links include the repository's configured referral parameters. Removing attribution fields makes the record incomplete and removes it from the generated manifest.

## Generated data policy

Files under `place_photos/`, along with `manifest.json` and `version.json`, are managed by the repository scripts and workflow.

Normal country, subdivision, and city additions, removals, renames, and path changes should be made in the private source place tree first, then synchronized through the workflow. Region membership in `place_photos/world.json` is maintained separately. Manual changes should be limited to deliberate repairs.

See also:

- [`github-actions.md`](github-actions.md)
- [`photo-selection.md`](photo-selection.md)
- [`sync-and-cleanup.md`](sync-and-cleanup.md)
