# Photo Selection

## Purpose

`generate_place_photos.py` selects eligible place entries, builds deterministic Unsplash queries, chooses one result, and writes complete photo metadata back to the public photo tree.

The selection policy is intentionally simple. It favors predictable behavior, bounded scheduled work, and future retries instead of permanent failure markers or complex ranking rules.

## Candidate selection

Normal runs process entries whose `image_url` is not an actual non-empty string. This includes ordinary empty-string placeholders as well as missing, `null`, or otherwise non-string values that need repair. Other missing metadata does not make an entry eligible when `image_url` is already a valid non-empty string.

Eligible blank candidates include:

- empty placeholder arrays whose place ID can be inferred from the file path
- photo records with an empty `image_url`
- photo records whose `image_url` is missing or not a string

Blank candidates use deterministic path order. Normal runs rotate that order through `photo_cursor.json` so repeated no-result entries cannot permanently block later candidates.

When `--overwrite` is used, only entries that already have an actual non-empty string `image_url` are eligible. Existing photos are processed from the oldest `cached_at` value first. Missing, non-string, or invalid timestamps are treated as the oldest. Overwrite mode does not use or update the blank-entry cursor.

## Cursor behavior

`photo_cursor.json` has this shape:

```json
{
  "last_attempted_place_id": "city:belize:toledo:punta_gorda"
}
```

The value is operational state and changes as normal runs progress. The example above is illustrative rather than a permanent expected value.

For normal blank-filling runs:

- processing resumes immediately after `last_attempted_place_id`
- candidate order wraps to the beginning after reaching the end
- the cursor advances after every attempted candidate, including no-result and recognized rate-limit attempts
- cursor position is resolved against the full photo tree, so a successfully filled entry can still be used as the resume point even though it is no longer in the blank queue
- if the saved place ID no longer exists, processing starts from the beginning and logs a warning
- cursor-only changes are committed but do not bump `version.json`

The cursor is operational workflow state. It is not included in `manifest.json` and does not change which photo records are considered complete.

### Why the cursor is necessary

A small attempt limit keeps each scheduled run reliable, but without persistent position every run would begin with the same blank entries. Places that repeatedly return no results could consume the whole batch forever while later candidates are never attempted.

The cursor preserves deterministic ordering while rotating the starting point. This gives the full queue a chance before earlier no-result entries are retried after wraparound.

## Attempt limit

The `--limit` value counts attempted place entries, not successful photo matches.

The default limit is `10`. The value must be `0` or greater, and `0` removes the attempt limit. Negative values are rejected before any photo processing begins.

One attempted place may generate more than one Unsplash request, but it still counts as one attempted entry.

### Why the limit counts attempts

Counting successful matches would make run length depend on Unsplash search quality. When many queries return no results, a success-based limit can continue through a large part of the queue, consume the available API quota, or reach the workflow timeout without finding the requested number of photos.

Counting attempts provides a predictable amount of work regardless of result quality. This is especially important for the automatic three-hour schedule, which uses the default limit of `10`.

The attempt limit and cursor solve different problems:

- the attempt limit bounds work within one run
- the cursor carries queue progress across runs

`limit=0` removes the attempt bound but does not remove the Unsplash quota or workflow timeout. It should be used deliberately for manual runs.

## Path and place ID behavior

Photo queries are built from both the stored `place_id` and the file path.

The stored ID is preferred when it is a non-empty string, structurally valid, and agrees with the path. When the stored value is missing, not a string, structurally invalid, or conflicts with the path labels, the path is used as the safer fallback source of truth.

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

An attempted entry is not the same as an API request. A city may use both its primary and fallback query, so one attempt can consume two requests when the first query has no result.

The search response must be a JSON object whose `results` field is a list. Unexpected response shapes are treated as real failures rather than being silently interpreted as no results.

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

The generated record is written only when `place_id`, `image_url`, `photographer_name`, `photographer_url`, and `source_url` are all actual non-empty strings. Missing, `null`, numeric, boolean, array, or object values do not pass validation and cause an incomplete Unsplash result to fail rather than enter the public manifest.

## No-result behavior

When all queries for a place return no results:

- no photo metadata is written
- in normal mode, the blank entry remains blank and eligible for a future cycle
- in overwrite mode, the existing photo record remains unchanged
- the run continues to the next candidate

No-result entries are normal and do not make the workflow fail. The normal-mode cursor still advances so later candidates receive a chance before the queue wraps back.

If the whole batch produces no photo or manifest changes, the script logs that outcome and exits successfully. A cursor-only commit is expected when normal-mode queue progress changed.

## Rate limits and failures

Unsplash quota exhaustion is treated as a warning rather than an error. The clean-stop path recognizes:

- HTTP 429
- HTTP 403 only when `X-Ratelimit-Remaining` is `0` and the response body says `Rate Limit Exceeded`

The current candidate is left unchanged, processing stops cleanly, and the normal-mode cursor records that attempted place before the script exits successfully.

The narrow HTTP 403 check is intentional. Other 403 responses may indicate authentication, permission, or request problems and must remain real failures rather than being hidden as quota exhaustion.

Other unexpected HTTP errors, network errors, malformed required data, unexpected response shapes, missing configuration, malformed cursor data in normal mode, and invalid negative limits remain real failures. They should not be hidden by broadly ignoring exit codes.

## Relationship to generated data

After candidate processing, `manifest.json` is rebuilt from complete usable photo records whose required fields are actual non-empty strings.

`version.json` is bumped only when photo metadata or the manifest changes. Search attempts and cursor-only updates do not bump the version because clients do not need to refresh public photo data for workflow-state-only changes.

A successful workflow run can therefore have several valid outcomes:

- photo or manifest changes with a version bump
- cursor-only progress with a commit but no version bump
- no tracked changes and no commit
- a clean stop after recognized quota exhaustion

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`github-actions.md`](github-actions.md): Workflow inputs, secrets, reliability design, result summaries, graceful outcomes, and real failures.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
