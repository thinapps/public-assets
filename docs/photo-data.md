# Photo Data

## Purpose

This repository stores public photo metadata without storing image binaries. Photo records point to external image URLs and include photographer and source attribution links.

Country, subdivision, and city photo paths are generated from a private source place tree. Region records in `place_photos/world.json` are maintained separately. Generated structure and ordering should remain deterministic, compact, and safe for clients to cache.

## Public files

- `place_photos/` contains the public photo metadata tree.
- `place_photos/world.json` contains region-level photo records.
- `place_photos/countries/` contains country, subdivision, and city photo records.
- `manifest.json` lists place IDs with complete usable photo metadata.
- `photos.json` is a generated place-ID lookup containing complete usable photo metadata for bulk consumers such as Freebase.top static builds.
- `version.json` contains the integer public payload version.

`photo_cursor.json` is separate operational workflow state. It helps normal photo generation resume through the blank-entry queue and is not part of the public photo payload or manifest.

## Why the bulk lookup lives here

`photos.json` is intentionally generated in this repository even though Freebase.top is currently its main bulk consumer.

The lookup is not required for the Android app and is not a new source of truth. It is a generic derived export of photo metadata already owned by this repository.

Keeping the export beside the canonical photo tree has several advantages:

- one producer owns normalization and eligibility rules
- every consumer sees the same complete photo metadata for a `place_id`
- bulk consumers can make one small request instead of downloading and scanning the entire repository archive
- consumers do not need to understand the internal `place_photos/` directory layout
- future consumers can reuse the same lookup instead of independently rebuilding it
- the existing photo workflow can regenerate the lookup atomically with the underlying metadata

The alternative would be for Freebase.top and any future bulk consumer to download the whole repository ZIP and derive an equivalent mapping on every build. That works and remains useful as a fallback, but it transfers more data, performs more parsing, couples consumers to this repository's internal file layout, and duplicates lookup-generation logic outside the repository that owns the data.

For those reasons, `photos.json` is the preferred normal interface for bulk consumers. Archive scanning is a resilience/bootstrap mechanism, not the primary architecture.

This repository should still remain presentation-agnostic. It owns photo metadata and generic derived exports only. Website HTML, CSS, image placement, SEO markup, and other Freebase.top-specific behavior belong in `thinapps/freebase.top`.

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

An entry with an empty string `image_url` is a valid placeholder and remains eligible for future photo searches. A missing or non-string `image_url` is incomplete and is treated as needing repair during normal candidate selection. Records missing other required fields remain incomplete and are excluded from `manifest.json` and `photos.json`.

A photo is complete and usable only when all of these fields contain actual non-empty JSON strings:

- `place_id`
- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`

Values of other JSON types, including `null`, numbers, booleans, arrays, and objects, do not satisfy the schema even when converting them to text would produce a non-empty value.

`cached_at` records when the cached photo metadata was written. It is optional for manifest and lookup eligibility and stale-photo migration. Missing, non-string, or invalid timestamps are treated as oldest when overwrite ordering is calculated.

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

When a stored `place_id` conflicts with a normal country, subdivision, or city file path, photo query generation treats the path as the safer fallback source of truth. A missing or non-string stored ID also falls back to the path when possible. `world.json` is a shared exception: its region records use their stored `region:*` IDs because the file path cannot identify an individual region.

## Manifest

`manifest.json` is rebuilt from complete usable photo records only.

It intentionally excludes:

- blank placeholders
- incomplete photo records
- records whose required fields are not strings
- files with invalid non-list payloads
- `photo_cursor.json`

The manifest contains unique place IDs in deterministic sorted order.

Clients can use the manifest to determine whether usable cached photo metadata exists before requesting a place file.

## Photo lookup

`scripts/build_photo_lookup.py` scans the same `place_photos/` tree and writes `photos.json`. The lookup is regenerated by the existing photo workflow after normal photo generation, so it remains a derived view rather than a second source of truth.

The root object is keyed by canonical `place_id`. Each value contains only the fields required by bulk consumers:

```json
{
  "city:costa_rica:guanacaste:tamarindo": {
    "image_url": "https://images.unsplash.com/...",
    "photographer_name": "Example Photographer",
    "photographer_url": "https://unsplash.com/@example?...",
    "source_url": "https://unsplash.com/photos/example?..."
  }
}
```

`cached_at` is intentionally omitted because bulk rendering does not need it. Keys are written in deterministic sorted order. If the source tree contains conflicting usable metadata for the same `place_id`, generation fails instead of choosing one record silently.

The lookup exists to prevent bulk clients from fetching thousands of individual metadata files or parsing the repository archive during normal operation. Per-place clients such as the Android app can continue using `manifest.json` plus the existing individual photo paths.

The lookup must be treated as generated output. Do not edit `photos.json` manually to repair a photo. Repair the canonical record under `place_photos/` and let the workflow rebuild the lookup.

## Consumer responsibilities

Bulk consumers should:

- treat `photos.json` as a read-only derived export
- match records by canonical `place_id`
- preserve `image_url`, photographer attribution, photographer URL, and source URL together
- validate the lookup before publishing output based on it
- tolerate a place having no photo
- avoid turning this repository into a presentation layer

Freebase.top additionally has a repository-ZIP fallback for bootstrap/resilience. That fallback deliberately reconstructs the same mapping from canonical `place_photos/` records and does not become a second source of truth.

## Manifest growth and scaling

The current single-file manifest should remain the default while its download size and parse time are comfortably small. A large line count in GitHub is not by itself a reason to split it. Pretty-printed JSON makes the file look larger than its operational cost, and one request is usually simpler and cheaper than several smaller requests.

Clients should avoid downloading the manifest on every use. The expected pattern is to check `version.json`, download `manifest.json` only when the public payload version changes or no cached copy exists, cache it locally, and parse the place IDs into a set for fast membership checks. This keeps the current design efficient even as the number of IDs grows.

Before introducing multiple files, consider these lower-cost options:

- keep the manifest cached and version-gated
- measure actual download and parse time rather than judging by line count
- write compact JSON if transfer size becomes meaningful
- consider a manifest-specific version or content hash if unrelated public payload changes cause unnecessary manifest downloads

Sharding should be considered only when the single manifest becomes a measurable network, memory, or parsing problem. A practical warning point is when it approaches roughly 1–2 MB, but observed client performance should decide the change rather than a fixed size alone.

JSON does not define a universal manifest-index format. If sharding becomes necessary, this repository must define and document its own stable schema. The usual pattern is a small root manifest that points to child manifests, similar in concept to an XML sitemap index:

```text
manifest.json
manifests/
├── regions.json
├── countries.json
├── cities-africa.json
├── cities-asia.json
├── cities-europe.json
└── cities-other.json
```

For example:

```json
{
  "schema_version": 2,
  "shards": [
    "manifests/regions.json",
    "manifests/countries.json",
    "manifests/cities-africa.json",
    "manifests/cities-asia.json",
    "manifests/cities-europe.json",
    "manifests/cities-other.json"
  ]
}
```

Shards should use deterministic names and stable boundaries, such as place type and geographic region. Each shard should preserve unique sorted IDs and the same eligibility rules as the current manifest.

Sharding is useful only when clients can load the necessary shards selectively or cache unchanged shards independently. If every client must download every child manifest to rebuild the same global set, sharding adds requests and implementation complexity without reducing the total data transferred. Any future migration must therefore update repository generation, versioning, client fetching, caching, failure handling, and backward compatibility together.

The same principle applies to `photos.json`: keep the single lookup while its actual transfer and parse cost remains reasonable. Shard only when measurement shows a real problem and consumers can benefit from selective loading.

## Version

`version.json` is bumped when generated public output changes in a way clients should notice. This includes:

- newly cached photo metadata
- refreshed photo metadata in overwrite mode
- manifest changes caused by place additions, removals, or stale-file cleanup

The file must contain a `version` field whose value is a JSON integer. Missing fields, numeric strings, floating-point values, booleans, and other JSON types are invalid and cause a required version bump to fail rather than silently resetting or coercing the counter.

Placeholder-only synchronization may be committed without a version bump when it does not change usable photo metadata or the manifest.

No version bump occurs when a run attempts searches but produces no public data changes. Cursor-only changes also do not bump the version.

If photo metadata or the manifest changes and `version.json` is missing, generation fails instead of silently skipping the required bump or creating a replacement counter.

## Photo attribution

Each usable photo record preserves:

- the external image URL
- the photographer name
- a photographer profile URL
- the original photo source URL

Photographer and source links include the repository's configured referral parameters. Removing attribution fields makes the record incomplete and removes it from the generated manifest and lookup.

## Generated data policy

Files under `place_photos/`, along with `manifest.json`, `photos.json`, `version.json`, and `photo_cursor.json`, are managed by the repository scripts and workflow.

Normal country, subdivision, and city additions, removals, renames, and path changes should be made in the private source place tree first, then synchronized through the workflow. Region membership in `place_photos/world.json` is maintained separately. Manual changes should be limited to deliberate repairs.

See also:

- [`github-actions.md`](github-actions.md)
- [`photo-selection.md`](photo-selection.md)
- [`sync-and-cleanup.md`](sync-and-cleanup.md)
- [`unsplash-compliance.md`](unsplash-compliance.md)
