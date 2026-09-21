# Photo Selection

## Purpose

`scripts/generate_place_photos.py` selects eligible place entries, builds deterministic Unsplash queries, chooses one result, and writes complete photo metadata back to the public photo tree.

The selection policy is intentionally simple. It favors predictable behavior, bounded workflow runs, and future queue cycles instead of permanent failure markers or complex ranking rules.

## Candidate selection

Every run uses one combined candidate flow. Incomplete records keep priority, while bounded runs reserve part of their attempt capacity for refreshing complete cached photos so older assignments cannot be starved indefinitely by a large incomplete queue.

Incomplete candidates fall into two groups:

- repair candidates: records that already have a non-empty `image_url` but are missing or have invalid required metadata such as `place_id`, `photographer_name`, `photographer_url`, or `source_url`
- blank candidates: empty placeholder arrays or records whose `image_url` is missing, empty, or not a string

Repair candidates are placed ahead of ordinary blank candidates before cursor rotation. Each group uses deterministic path order, while the existing cursor and wraparound behavior still allows later candidates to make progress when earlier repairs repeatedly return no results.

A repair does not attempt to reconstruct attribution from an existing image URL. The generator searches the place again and, when it finds a usable result, replaces the incomplete assignment with a complete API-derived record and performs the normal Unsplash download-location tracking for that newly persisted selection.

Complete usable photo records form the refresh queue and are ordered from the oldest `cached_at` value first. Missing, non-string, or invalid timestamps are treated as the oldest. Refresh candidates do not use or update the repair-and-fill cursor.

When both queues are non-empty and `--limit` is bounded, the generator reserves roughly one quarter of the attempt limit for refreshes, capped at five attempts. The normal `limit=20` therefore schedules up to 15 repair-or-fill attempts plus 5 refresh attempts; `limit=10` schedules up to 8 plus 2. If fewer incomplete candidates are available, unused capacity flows to additional refreshes. A one-attempt run still keeps incomplete work first. `limit=0` remains unbounded and processes the full repair-and-fill queue before continuing through refresh candidates.

When a refresh search selects the same underlying Unsplash photo, the generator recognizes it from the stable `images.unsplash.com` host and URL path while ignoring volatile query parameters. It retains the existing image URL so parameter churn alone does not create a replacement. If all other public metadata is also unchanged, only `cached_at` is refreshed; if attribution metadata changed for that same photo, the metadata is updated and the public version changes without triggering a new download-selection event.

This keeps incomplete data as the higher-priority queue while guaranteeing regular bounded refresh progress, so older complete assignments are eventually reconsidered with the current search and selection logic even when incomplete records remain.

## Cursor behavior

`photo_cursor.json` has this shape:

```json
{
  "last_attempted_place_id": "city:belize:toledo:punta_gorda"
}
```

The value is operational state and changes as the repair-and-fill portion of runs progresses. The example above is illustrative rather than a permanent expected value.

For repair-and-fill candidates:

- processing resumes immediately after `last_attempted_place_id`
- candidate order wraps to the beginning after reaching the end
- the cursor advances after every attempted repair or blank candidate, including no-result attempts and recognized rate-limit attempts
- cursor position is resolved against the full photo tree, so a successfully repaired or filled entry can still be used as the resume point even though it is no longer in the incomplete queue
- if the saved place ID no longer exists, processing starts from the beginning and logs a warning
- cursor-only changes are committed but do not bump `version.json`

Refresh candidates do not move the cursor. When a bounded run schedules both repair-or-fill work and reserved refresh work, the cursor stays at the last repair-or-fill candidate attempted during that run.

The cursor is operational workflow state. It is not included in `manifest.json` and does not change which photo records are considered complete.

### Why the cursor is necessary

A small attempt limit keeps each workflow run reliable, but without persistent position every run would begin with the same incomplete entries. Places that repeatedly return no results could consume the repair-and-fill share forever while later incomplete candidates are never attempted.

The cursor preserves deterministic ordering while rotating the starting point. This gives the full repair-and-fill queue a chance before earlier no-result entries are retried after wraparound.

Complete refresh candidates do not need the cursor because they are already ordered by `cached_at`, so successfully refreshed or revalidated records naturally move toward the back of the refresh queue with their new timestamp.

## Attempt limit

The `--limit` value counts attempted place entries, not successful photo matches.

The default limit is `20`. The value must be `0` or greater, and `0` removes the attempt limit. Negative values are rejected before any photo processing begins.

One attempted place may generate more than one Unsplash request, but it still counts as one attempted entry.

### Why the limit counts attempts

Counting successful matches would make run length depend on Unsplash search quality. When many queries return no results, a success-based limit can continue through a large part of the queue, consume the available API quota, or reach the workflow timeout without finding the requested number of photos.

Counting attempts provides a predictable amount of work regardless of result quality. Scheduled and manual workflow runs use the default limit of `20` unless a manual run supplies another value.

For bounded runs where both incomplete and refresh candidates exist, the refresh reserve is calculated as roughly 25% of `limit`, capped at five and constrained by the number of available refresh candidates. At least one repair-or-fill attempt remains ahead of refresh work for a one-item run. This gives refreshes guaranteed recurring capacity without removing incomplete-data priority.

The attempt limit, refresh reserve, and cursor solve different problems:

- the attempt limit bounds total work within one run across repair, fill, and refresh candidates
- the refresh reserve prevents complete-photo refreshes from being starved by a permanently large incomplete queue
- the cursor carries repair-and-fill queue progress across runs

`limit=0` removes the attempt bound and therefore does not use a reserve split; the generator processes the full repair-and-fill queue before the full refresh queue. Unsplash quota and the workflow timeout still apply, so unbounded runs should be used deliberately.

## Path and place ID behavior

Photo queries are built from both the stored `place_id` and the file path.

A recognized non-empty string ID is preferred when it agrees with the normal file path. When the stored value is missing, not a string, too short for its place type, or conflicts with the path labels, the path is used as the safer fallback source of truth.

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
- `per_page=10`
- `order_by=relevant`
- `orientation=landscape`
- `content_filter=high`

`order_by=relevant` is set explicitly even though it is currently the Unsplash default, because the ranking logic depends on the API returning the closest matches first.

The workflow uses `UNSPLASH_ACCESS_KEY` for authentication.

An attempted entry is not the same as an API request. A city may use both its primary and fallback query, so one attempt can consume two requests when the first query has no result. Returning 10 results instead of 3 does not add another search request.

The search response must be a JSON object whose `results` field is a list. Unexpected response shapes are treated as real failures rather than being silently interpreted as no results.

## Result selection

Unsplash returns search results in relevance order. The script considers only the first three original result positions and applies relevance weights of `4`, `2`, and `1`. Each candidate's weighted score is `(valid likes + 1) × relevance weight`, so even a zero-like top result keeps a real relevance advantage instead of collapsing to a score of zero. Result #2 or #3 can still win when it is substantially more liked, and exact weighted-score ties go to the earlier, more relevant result.

Malformed non-object entries are ignored without compressing their original result positions, so a valid item originally returned as result #2 cannot accidentally receive the #1 relevance weight merely because result #1 was malformed.

This keeps Unsplash relevance as the dominant signal while retaining likes as a simple quality signal. The script does not currently use description keyword filters or add generic terms such as `skyline`, `downtown`, or `landscape` to every query.

Image width, height, area, and file size are not used for ranking. The selected `regular` image URL already provides the standard display-sized image used by this repository.

The chosen record stores:

- the regular image URL
- photographer name
- photographer profile URL
- original photo source URL
- the current UTC `cached_at` timestamp

Photographer and source links retain the configured Unsplash referral parameters.

The generated record is written only when `place_id`, `image_url`, `photographer_name`, `photographer_url`, and `source_url` are all actual non-empty strings. Missing, `null`, numeric, boolean, array, or object values do not pass validation and cause an incomplete Unsplash result to fail rather than enter the public manifest.

For an existing complete Unsplash record, photo identity is determined from the `images.unsplash.com` host and URL path, ignoring the image URL query string. Matching identities are treated as the same underlying photo even when API-generated URL parameters differ. The existing image URL is retained in that case. If photographer or source metadata changed, those public fields are updated and versioned without a new download event; when they are also unchanged, only `cached_at` advances.

## No-result behavior

When all queries for a place return no results:

- no photo metadata is written
- an incomplete existing record remains unchanged and eligible for a future repair cycle
- a blank entry remains blank and eligible for a future fill cycle
- an existing complete photo remains unchanged when its refresh attempt finds no replacement
- the run continues to the next candidate

No-result entries are normal and do not make the workflow fail. The cursor still advances for repair-and-fill attempts so later incomplete candidates receive a chance before that queue wraps back. Refresh attempts do not move the cursor.

If the whole batch produces no photo or manifest changes, the script logs that outcome and exits successfully. A cursor-only commit is expected when repair-and-fill queue progress changed. A cache-only refresh can also produce a commit without changing the public payload version.

## Rate limits and failures

Unsplash quota exhaustion is treated as a warning rather than an error. The clean-stop path recognizes:

- HTTP 429
- HTTP 403 only when `X-Ratelimit-Remaining` is `0` and the response body says `Rate Limit Exceeded`

The current candidate is left unchanged and processing stops cleanly. If the rate limit is reached while attempting a repair-or-fill candidate, the cursor records that attempted place before the script exits successfully. If it is reached during a refresh candidate, the repair-and-fill cursor remains unchanged from its latest position.

The narrow HTTP 403 check is intentional. Other 403 responses may indicate authentication, permission, or request problems and must remain real failures rather than being hidden as quota exhaustion.

Other unexpected HTTP errors, network errors, malformed required data, unexpected response shapes, missing configuration, malformed cursor data, and invalid negative limits remain real failures. They should not be hidden by broadly ignoring exit codes.

## Relationship to generated data

After candidate processing, `manifest.json` is rebuilt from complete usable photo records whose required fields are actual non-empty strings.

During generation, `version.json` is bumped when public photo metadata or the rebuilt manifest changes. The workflow then rebuilds `photos.json`; if that lookup changes without an earlier version change in the same run, the workflow bumps `version.json` once for the lookup-only public payload change. Search attempts, cursor-only updates, and cache-only `cached_at` refreshes do not bump the version because they do not change public photo output.

A successful workflow run can therefore have several valid outcomes:

- a repaired incomplete record or newly filled blank with a version bump
- a changed refreshed photo with a version bump
- an unchanged photo revalidated with only `cached_at` refreshed and no version bump
- other photo or manifest changes with a version bump
- a lookup-only `photos.json` change with one workflow version bump
- cursor-only progress with a commit but no version bump
- no tracked changes and no commit
- a clean stop after recognized quota exhaustion

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`github-actions.md`](github-actions.md): Workflow inputs, secrets, reliability design, result summaries, graceful outcomes, and real failures.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
- [`unsplash-compliance.md`](unsplash-compliance.md): Unsplash hotlinking, attribution, tracking, API-key, and workflow compliance requirements.
