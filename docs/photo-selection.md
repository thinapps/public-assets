# Photo Selection

## Purpose

`generate_place_photos.py` selects eligible place entries, builds deterministic Unsplash queries, chooses one result, and writes complete photo metadata back to the public photo tree.

The selection policy is intentionally simple. It favors predictable behavior, small batches, and future retries instead of permanent failure markers or complex ranking rules.

## Candidate selection

Normal runs process only entries whose `image_url` is empty. Other missing metadata does not make an entry eligible when `image_url` is already filled.

Eligible blank candidates include:

- empty placeholder arrays whose place ID can be inferred from the file path
- photo records with an empty `image_url`

Blank candidates use deterministic path order. Normal runs rotate that order through `photo_cursor.json` so repeated no-result entries cannot permanently block later candidates.

When `--overwrite` is used, only entries that already have an `image_url` are eligible. Existing photos are processed from the oldest `cached_at` value first. Missing or invalid timestamps are treated as the oldest. Overwrite mode does not use or update the blank-entry cursor.

## Cursor behavior

`photo_cursor.json` stores:

```json
{
  "last_attempted_place_id": "city:belize:toledo:barranco"
}
```

For normal blank-filling runs:

- processing resumes immediately after `last_attempted_place_id`
- candidate order wraps to the beginning after reaching the end
- the cursor advances after every attempted candidate, including no-result and recognized rate-limit attempts
- cursor position is resolved against the full photo tree, so a successfully filled entry can still be used as the resume point even though it is no longer in the blank queue
- if the saved place ID no longer exists, processing starts from the beginning and logs a warning
- cursor-only changes are committed but do not bump `version.json`

The cursor is operational workflow state. It is not included in `manifest.json` and does not change which photo records are considered complete.

## Attempt limit

The `--limit` value counts attempted place entries, not successful photo matches.

The default limit is `10`. The value must be `0` or greater, and `0` removes the attempt limit. Negative values are rejected before any photo processing begins.

One attempted place may generate more than one Unsplash request, but it still counts as one attempted entry.

## Path and place ID behavior

Photo queries are built from both the stored `place_id` and the file path.

The stored ID is preferred when it is structurally valid and agrees with the path. When the place type or path labels conflict with the stored ID, the path is used as the safer fallback source of truth.

`world.json` is a shared exception: its region records use their stored `region:*` IDs because the file path cannot identify an individual region.

Path slugs use dashes while place IDs use underscores. Query labels convert both forms into readable title-cased words.

## Query rules

Queries remain plain and deterministic:

- region: `Region`
- country: `Country`
- subdivision: `Subdivision Country`
- city primary: `City Subdivision`
- city fallback: `City Country`

Queries are tried in order, and the first query that returns results wins. Results from multiple queries are not combined.

When the city and subdivision labels are identical, the duplicated `City Subdivision` query is skipped and only `City Country` is used.

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
- in normal mode, the blank entry remains blank and eligible for a future cycle
- in overwrite mode, the existing photo record remains unchanged
- the run continues to the next candidate

No-result entries are normal and do not make the workflow fail. The normal-mode cursor still advances so later candidates receive a chance before the queue wraps back.

If the whole batch produces no photo or manifest changes, the script logs that outcome and exits successfully.

## Rate limits and failures

Unsplash quota exhaustion is treated as a warning rather than an error. The clean-stop path recognizes HTTP 429 and Unsplash's HTTP 403 response when `X-Ratelimit-Remaining` is `0` and the response says `Rate Limit Exceeded`. The current candidate is left unchanged, processing stops cleanly, and the normal-mode cursor records that attempted place before the script exits successfully.

Other HTTP 403 responses and other unexpected HTTP errors, network errors, malformed required data, missing configuration, malformed cursor data, and invalid negative limits remain real failures. They should not be hidden by broadly ignoring exit codes.

## Relationship to generated data

After candidate processing, `manifest.json` is rebuilt from complete usable photo records.

`version.json` is bumped only when photo metadata or the manifest changes. Search attempts and cursor-only updates do not bump the version.

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`github-actions.md`](github-actions.md): Workflow inputs, secrets, graceful outcomes, and real failures.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
