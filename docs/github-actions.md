# GitHub Actions

## Update Place Photos

The `Update Place Photos` workflow is defined in `.github/workflows/update-place-photos.yml`.

It keeps country, subdivision, and city photo paths synchronized with the private source place tree, searches Unsplash for eligible photos across the public photo tree, advances the repair-and-fill cursor, reserves bounded capacity to refresh older complete assignments, rebuilds the public manifest and bulk photo lookup, bumps `version.json` when public photo output changes, and commits any resulting updates. Region membership in `place_photos/world.json` is maintained separately.

## Schedule and manual runs

The workflow runs automatically every three hours at 17 minutes past the hour using the UTC cron expression `17 */3 * * *`. It can also be started on demand from the GitHub Actions tab with `workflow_dispatch`.

Scheduled runs use the normal default limit of `20`, so they remain bounded rather than attempting the full queue. Manual runs can override that limit when deliberate maintenance requires a different batch size.

Manual runs support one input:

- `limit`: Maximum number of eligible place entries to attempt. The default is `20`. The value must be `0` or greater, and `0` removes the attempt limit.

The limit counts attempted place entries, not successful photo matches. A place may use more than one Unsplash search query, but it still counts as one attempted entry.

Each run resumes after `photo_cursor.json` and rotates through the deterministic repair-and-fill queue. Repair candidates with an existing image but incomplete required metadata are prioritized ahead of ordinary blank candidates before cursor rotation. When both incomplete and complete refresh candidates exist in a bounded run, roughly one quarter of the attempt limit is reserved for oldest-first complete-photo refreshes, capped at five attempts. The normal `limit=20` therefore schedules up to 15 repair-or-fill attempts plus 5 refresh attempts. Refresh attempts do not move the repair-and-fill cursor.

## Reliability design

Runs combine an attempt-based limit, a bounded refresh reserve, and a persistent repair-and-fill cursor. The limit bounds work within each run, the reserve guarantees recurring complete-photo refresh progress, and the cursor lets later runs resume after the last attempted incomplete place so repeated no-result entries do not permanently block the repair-and-fill queue.

Together, these rules provide:

- predictable run time
- bounded Unsplash quota usage within one run
- steady progress through the repair-and-fill queue
- automatic repair of incomplete records that would otherwise remain unusable
- continuous oldest-first refresh of complete assignments even while incomplete records remain
- structural recovery for syntactically valid country-tree photo JSON that no longer matches the canonical array/object shape
- successful no-change outcomes when nothing is wrong
- real failures for configuration, data, network, and unexpected API problems

The 15-minute job timeout remains a final safety backstop rather than the normal batch-control mechanism. See [`photo-selection.md`](photo-selection.md) for the detailed candidate-ordering, attempt-limit, refresh-reserve, and cursor rationale.

## Concurrency

All runs use the `update-place-photos` concurrency group, so only one update run executes at a time.

`cancel-in-progress` is disabled. A newly triggered run does not cancel the run already in progress. With the default GitHub Actions queue behavior, at most one additional run remains pending; a newer pending run may replace an older pending run in the same concurrency group.

The concurrency group only coordinates this workflow. A separate manual or web commit can still reach the branch while a run is active. Before pushing, the workflow fetches the latest branch and rebases its generated commit. It retries a non-fast-forward push race up to three times. A real rebase conflict still fails rather than overwriting newer repository changes.

## Required secrets

The workflow requires:

- `SOURCE_REPOSITORY`: Private repository containing the source place tree.
- `SOURCE_REPOSITORY_TOKEN`: Token with read access to the private source repository.
- `SOURCE_PLACES_PATH`: Path to the source countries directory inside that repository.
- `UNSPLASH_ACCESS_KEY`: Unsplash API access key used for photo searches.

Missing or invalid configuration is treated as a real failure.

## Run sequence

1. Check out this public repository.
2. Check out the private source repository without persisting its credentials.
3. Set up Python 3.11.
4. Synchronize country, subdivision, and city photo placeholders with the current source place tree and normalize recoverable valid-JSON structural problems into canonical public records.
5. Migrate usable cached photos when a place path changes and safely prune stale files.
6. Resume after the stored repair-and-fill cursor and schedule incomplete repair candidates and blank fill candidates first within the bounded run mix.
7. Reserve the bounded refresh share for complete cached photos ordered from the oldest `cached_at` value first. The same underlying Unsplash photo is recognized from the stable image host and path while query parameters are ignored. Same-photo refreshes keep the existing image URL, update changed attribution metadata without a new download-selection event, and otherwise refresh only `cached_at`. If all refresh queries return no replacement, the existing public assignment is preserved and only `cached_at` advances so the checked record moves behind older unchecked refresh candidates. A different photo is persisted with normal Unsplash download tracking.
8. Save the last attempted repair-or-fill place ID in `photo_cursor.json` when that portion of the queue advanced.
9. Rebuild `manifest.json` from complete cached photo records.
10. Bump `version.json` when public photo metadata or the rebuilt manifest changes. Cache-only `cached_at` refreshes do not bump it.
11. Rebuild `photos.json` from complete canonical records for bulk consumers.
12. If `photos.json` changed but `version.json` did not already change during photo generation, bump `version.json` once for the lookup-only public payload change.
13. Commit any resulting changes, rebase that commit onto the latest branch state, and push with a limited retry for non-fast-forward races.

The lookup safeguard prevents a generated `photos.json` change from being published without a corresponding public payload version change. It first checks whether photo generation already changed `version.json`, so normal photo updates are not double-bumped.

## Generated commit shape

A successful workflow run should commit all generated changes from that run together as one combined commit. This is preferable to splitting each generated file into separate commits because the changed place-photo records, `photos.json`, `manifest.json`, `version.json`, and `photo_cursor.json` together represent one coherent pipeline state.

Keeping the run atomic avoids intermediate repository states where a place photo has changed but the lookup, public version, manifest, or cursor still reflects the previous state. It also keeps automated history easy to understand and makes a complete generated run simpler to inspect or revert. The one-file-per-commit rule for manual repository edits does not apply to these workflow-generated commits.

## Normal successful outcomes

The following conditions are normal and must complete successfully:

- Repair or fill candidates return no Unsplash results and remain eligible for a later queue cycle.
- A complete-photo refresh returns no replacement and only advances `cached_at` so refresh ordering continues progressing.
- A refresh reselects the same underlying Unsplash photo and, when other public metadata is unchanged, only advances `cached_at`.
- The configured attempt limit is reached without finding a different photo.
- Unsplash reports exhausted API quota through HTTP 429 or its recognized HTTP 403 rate-limit response.
- Only `photo_cursor.json` changes.
- The workflow produces no repository changes.

In all of these cases the scripts exit successfully. If no tracked files changed, the commit step reports `no changes to commit`; otherwise it commits the resulting synchronization, generated-data, cache-timestamp, or cursor changes.

A green run does not necessarily mean that a public photo was added, repaired, or changed. It means the workflow completed without an actionable failure. Cursor-only and cache-only commits are useful maintenance progress even when no public photo data changed.

Recognized quota-exhaustion responses are logged as warnings because they use the clean-stop path. Ordinary HTTP 403 responses and other unexpected HTTP responses are logged as errors and fail the run.

## Reading generation results

The generator prints a final summary containing:

- `eligible_candidates`: combined repair, fill, and refresh candidates available after repair-and-fill cursor rotation and refresh ordering
- `attempted_entries`: place entries processed during this run
- `changed_entries`: public photo records added, repaired, or changed during refresh
- `cache_refreshed_entries`: unchanged complete photo assignments whose `cached_at` timestamp was refreshed after a same-photo or completed no-result refresh
- `manifest_changed`: whether rebuilding `manifest.json` changed its contents
- `cursor_changed`: whether repair-and-fill workflow progress moved forward

When both queues are populated in a bounded run, the generator also logs the scheduled run mix as `repair_or_fill` and `refresh` counts. The normal default mix is up to `15 + 5` for `limit=20`, while smaller limits scale the refresh share to roughly one quarter, capped at five.

The generator also prints `last_attempted_place_id` when at least one repair-or-fill candidate was attempted. Refresh-only runs do not move or reprint the cursor as new progress.

Typical outcomes include:

- `changed_entries>0`: one or more public photo records were filled, repaired, or changed during refresh, so `version.json` is bumped
- `cache_refreshed_entries>0` with no other public changes: existing complete assignments were checked and moved back in refresh ordering after a same-photo or no-result refresh, without an Unsplash download event or version bump
- `manifest_changed=True`: usable public photo availability changed, so `version.json` is bumped
- a lookup-only `photos.json` change: the workflow bumps `version.json` once after rebuilding the lookup
- only `cursor_changed=True`: the repair-and-fill queue advanced and a cursor-only commit is expected, with no version bump
- all change fields false: no tracked generated state changed, so `no changes to commit` is expected
- a recognized quota warning: processing stopped cleanly at the current attempted place; repair-and-fill cursor progress is saved only when that part of the queue advanced

One attempted entry may issue multiple Unsplash requests because city candidates can have a primary and fallback query. Therefore `attempted_entries` is not the API request count.

## Real failures

The workflow should remain red for problems that require attention, including:

- Missing required secrets.
- Failure to check out the source repository.
- A missing or invalid source path.
- An invalid attempt limit, including a negative value.
- Unsafe stale-file pruning beyond the configured safety threshold.
- A missing `version.json` when public photo metadata, manifest, or lookup changes require a version bump.
- A missing or non-integer `version` field when a version bump is required.
- Unreadable or syntactically malformed public photo, manifest, lookup, or version JSON when those files are processed.
- Unreadable or syntactically malformed cursor JSON.
- Unexpected Unsplash response shapes, HTTP responses, or network failures other than recognized quota exhaustion.
- A Git rebase conflict or a push that still fails after the limited retry.

For current country, subdivision, and city paths, syntactically valid but structurally unsupported public JSON is normalized by the synchronization step before candidate generation. Recoverable object payloads preserve their string photo metadata; unusable scalar or non-object first-entry structures are reset to a canonical blank first record. Files outside the synchronization scope, such as `place_photos/world.json`, retain the generator's normal validation behavior and unsupported non-list payloads are skipped.

Individual records whose required photo fields are missing, empty, or not strings are treated as incomplete and become repair or fill candidates rather than usable cached photos.

Malformed source JSON is skipped by the synchronization script and does not fail the workflow by itself. A valid legacy `id` is used when `place_id` is missing, empty, or not a string.

Do not hide real failures by broadly ignoring command exit codes or increasing the workflow timeout.

## Timeout and manual batch sizing

The job timeout is 15 minutes. The default attempt limit of `20` is the normal control for scheduled runs and the default control for manual runs; the timeout is only the final backstop.

For larger manual batches, increase `limit` carefully. Each place can generate multiple Unsplash requests, and the script pauses between attempted entries. Bounded limits continue reserving roughly one quarter of capacity for refreshes, capped at five. `limit=0` removes both the attempt bound and the reserve split, so it processes the full repair-and-fill queue before refreshes; Unsplash quota and the job timeout still apply, so it should be reserved for deliberate manual runs.

## Manual maintenance

Use a manual `workflow_dispatch` run when you want an immediate on-demand update or a deliberately different batch size. Scheduled runs already perform the same synchronization, generation, lookup, versioning, and commit sequence every three hours with the default bounded limit.

For local diagnostics, `scripts/generate_place_photos.py` supports `--dry-run`. A dry run may still perform Unsplash searches for repair, fill, and refresh candidates, but it does not persist selected photo metadata or trigger download-location tracking. Keep diagnostic limits small and review the output before running without `--dry-run`.

Run `python scripts/build_photo_lookup.py` only to regenerate `photos.json` from already-correct canonical records under `place_photos/`. Repair canonical records rather than editing `photos.json` directly. If a local manual rebuild changes `photos.json`, ensure the corresponding public payload version is also bumped before publishing the change; the automatic lookup-only safeguard lives in the workflow.

Manual synchronization or stale pruning should use the documented source tree and existing safety guards. Review normalization, migration, and deletion output carefully, and do not bypass the 10% stale-delete protection merely to complete a run.

## Files involved

- `.github/workflows/update-place-photos.yml`: Workflow definition.
- `scripts/sync_place_photo_tree.py`: Synchronizes placeholders, normalizes recoverable public record structure, and prunes stale files safely.
- `scripts/generate_place_photos.py`: Prioritizes repair and fill candidates while reserving bounded capacity for oldest-first refresh candidates, rotates the incomplete queue through the cursor, searches Unsplash, writes complete photo records, refreshes unchanged cache timestamps, rebuilds the manifest, and updates the version when public output changes.
- `scripts/photo_queries.py`: Builds deterministic search queries from place IDs and paths.
- `scripts/build_photo_lookup.py`: Rebuilds the bulk `photos.json` lookup from complete canonical photo records.
- `photo_cursor.json`: Stores the last attempted place ID for the repair-and-fill portion of runs.
- `manifest.json`: Lists place IDs with complete usable photo records.
- `photos.json`: Generated place-ID lookup used by bulk consumers.
- `version.json`: Public payload version incremented when public photo output changes.

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`photo-selection.md`](photo-selection.md): Candidate ordering, cursor behavior, search queries, Unsplash settings, result selection, no-result, rate-limit, and failure behavior.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
- [`unsplash-compliance.md`](unsplash-compliance.md): Unsplash hotlinking, attribution, tracking, API-key, and workflow compliance requirements.
