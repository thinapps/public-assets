# Photo Selection

## Purpose

`generate_place_photos.py` selects eligible place entries, builds deterministic Unsplash queries, chooses one result, and writes complete photo metadata back to the public photo tree.

The selection policy is intentionally simple. It favors predictable behavior, small batches, and future retries instead of permanent failure markers or complex ranking rules.

## Candidate selection

Normal runs process only entries that are missing photo metadata. Filled entries are not considered unless `--overwrite` is used.

Eligible blank candidates include:

- empty placeholder arrays whose place ID can be inferred from the file path
- photo records with an empty `image_url`

Blank candidates are processed in deterministic path order.

When `--overwrite` is used, only entries that already have an `image_url` are eligible. Existing photos are processed from the oldest `cached_at` value first. Missing or invalid timestamps are treated as the oldest.

## Attempt limit

The `--limit` value counts attempted place entries, not successful photo matches.

The default limit is `10`. A value of `0` removes the attempt limit.

One attempted place may generate more than one Unsplash request, but it still counts as one attempted entry.

## Path and place ID behavior

Photo queries are built from both the stored `place_id` and the file path.

The stored ID is preferred when it is structurally valid and agrees with the path. When the place type or path labels conflict with the stored ID, the path is used as the safer fallback source of truth.

Path slugs use dashes while place IDs use underscores. Query labels convert both forms into readable title-cased words.

## Query rules

Queries remain plain and deterministic:

- region: `Region`
- country: `Country`
- subdivision: `Subdivision Country`
- city primary: `City Subdivision`
- city fallback: `City Country`

When a city name matches its subdivision name, only `City Country` is used to avoid a duplicated query such as `Singapore Singapore`.

Duplicate queries are removed case-insensitively while preserving their original order.

## Unsplash request settings

Each search request uses:

- endpoint: `/search/photos`
- first result page only
- `per_page=3`
- `orientation=landscape`
- `content_filter=high`

The workflow uses `UNSPLASH_ACCESS_KEY` for authentication.

## Result selection

When Unsplash returns results, the script selects one photo by:

1. largest image area, calculated from width multiplied by height
2. highest like count when image areas are equal

The chosen record stores:

- the regular image URL
- photographer name
- photographer profile URL
- original photo source URL
- the current UTC `cached_at` timestamp

Photographer and source links retain the configured Unsplash referral parameters.

## No-result behavior

When all queries for a place return no results:

- no photo metadata is written
- the placeholder remains blank
- the entry remains eligible for a future run
- the run continues to the next candidate

No-result entries are normal and do not make the workflow fail.

If the whole batch produces no photo or manifest changes, the script logs that outcome and exits successfully.

## Rate limits and failures

Unsplash HTTP 429 is treated as quota exhaustion. The current candidate is left unchanged, processing stops cleanly, and the script exits successfully after rebuilding the manifest as needed.

Other unexpected HTTP errors, network errors, malformed required data, and missing configuration remain real failures. They should not be hidden by broadly ignoring exit codes.

## Relationship to generated data

After candidate processing, `manifest.json` is rebuilt from complete usable photo records.

`version.json` is bumped only when photo metadata or the manifest changes. Search attempts with no resulting public data changes do not bump the version.

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`github-actions.md`](github-actions.md): Workflow inputs, secrets, graceful outcomes, and real failures.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.