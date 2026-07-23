# GitHub Actions

## Update Place Photos

The `Update Place Photos` workflow is defined in `.github/workflows/update-place-photos.yml`.

It keeps country, subdivision, and city photo paths synchronized with the private source place tree, searches Unsplash for eligible photos across the public photo tree, advances the normal blank-entry cursor, rebuilds the public manifest, bumps `version.json` when cached photo metadata or the rebuilt manifest changes, and commits any resulting updates. Region membership in `place_photos/world.json` is maintained separately.

## Schedule and manual runs

The workflow runs automatically every three hours at 17 minutes past the hour. It can also be started manually from the GitHub Actions tab.

Manual runs support these inputs:

- `limit`: Maximum number of eligible place entries to attempt. The default is `20`. The value must be `0` or greater, and `0` removes the attempt limit.
- `overwrite`: When `true`, refresh existing photos instead of filling only blank entries. Existing photos are processed from the oldest cached entry first.

The limit counts attempted place entries, not successful photo matches. A place may use more than one Unsplash search query, but it still counts as one attempted entry.

Automatic scheduled runs have no manual input values, so they use the default limit of `20` and normal blank-filling mode.

Normal blank-filling runs resume after `photo_cursor.json` and wrap through the deterministic queue. Overwrite runs keep their separate oldest-photo-first order and do not change the cursor.

## Reliability design

Scheduled runs combine an attempt-based limit with a persistent cursor. The limit bounds work within each run, while the cursor lets later runs resume after the last attempted place so repeated no-result entries do not permanently block the queue.

Together, these rules provide:

- predictable normal run time
- lower risk of exhausting the Unsplash quota in one run
- steady progress through the blank-entry queue
- successful no-change outcomes when nothing is wrong
- real failures for configuration, data, network, and unexpected API problems

The 15-minute job timeout remains a final safety backstop rather than the normal batch-control mechanism. See [`photo-selection.md`](photo-selection.md) for the detailed attempt-limit and cursor rationale.

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
4. Synchronize country, subdivision, and city photo placeholders with the current source place tree.
5. Migrate usable cached photos when a place path changes and safely prune stale files.
6. Resume after the stored blank-entry cursor and attempt Unsplash searches for eligible places, unless overwrite mode is active.
7. Save the last attempted normal-mode place ID in `photo_cursor.json`.
8. Rebuild `manifest.json` from complete cached photo records.
9. Bump `version.json` when cached photo metadata or the rebuilt manifest changes.
10. Commit any resulting changes, rebase that commit onto the latest branch state, and push with a limited retry for non-fast-forward races.

## Normal successful outcomes

The following conditions are normal and must complete successfully:

- No eligible photo entries remain.
- The attempted places return no Unsplash results.
- The configured attempt limit is reached without finding a photo.
- Unsplash reports exhausted API quota through HTTP 429 or its recognized HTTP 403 rate-limit response.
- Only `photo_cursor.json` changes.
- The workflow produces no repository changes.

In all of these cases the scripts exit successfully. If no tracked files changed, the commit step reports `no changes to commit`; otherwise it commits the resulting synchronization, generated-data, or cursor changes.

A green run does not necessarily mean that a photo was added. It means the workflow completed without an actionable failure. Cursor-only commits are useful progress even when no public photo data changed.

Recognized quota-exhaustion responses are logged as warnings because they use the clean-stop path. Ordinary HTTP 403 responses and other unexpected HTTP responses are logged as errors and fail the run.

## Reading generation results

The generator prints a final summary containing:

- `eligible_candidates`: candidates available in the current mode after ordering and cursor rotation
- `attempted_entries`: place entries processed during this run
- `changed_entries`: photo records added or refreshed
- `manifest_changed`: whether rebuilding `manifest.json` changed its contents
- `cursor_changed`: whether normal-mode workflow progress moved forward

Normal runs also print `last_attempted_place_id` when at least one place was attempted.

Typical outcomes include:

- `changed_entries>0`: one or more photo records changed, so `version.json` is bumped
- `manifest_changed=True`: usable public photo availability changed, so `version.json` is bumped
- only `cursor_changed=True`: the queue advanced and a cursor-only commit is expected, with no version bump
- all change fields false: no tracked generated state changed, so `no changes to commit` is expected
- a recognized quota warning: processing stopped cleanly at the current attempted place and normal-mode cursor progress is still saved

One attempted entry may issue multiple Unsplash requests because city candidates can have a primary and fallback query. Therefore `attempted_entries` is not the API request count.

## Real failures

The workflow should remain red for problems that require attention, including:

- Missing required secrets.
- Failure to check out the source repository.
- A missing or invalid source path.
- An invalid attempt limit, including a negative value.
- Unsafe stale-file pruning beyond the configured safety threshold.
- A missing `version.json` when photo metadata or manifest changes require a version bump.
- A missing or non-integer `version` field when a version bump is required.
- Unreadable or syntactically malformed public photo or manifest JSON, or version JSON when a version bump is required.
- Unreadable or syntactically malformed cursor JSON during normal blank-filling mode.
- Unexpected Unsplash response shapes, HTTP responses, or network failures other than recognized quota exhaustion.
- A Git rebase conflict or a push that still fails after the limited retry.

Valid JSON photo files with unsupported non-list payloads are skipped from candidate and manifest processing. Individual records whose required photo fields are missing, empty, or not strings are treated as incomplete rather than usable cached photos.

Malformed source JSON is skipped by the synchronization script and does not fail the workflow by itself.

Do not hide real failures by broadly ignoring command exit codes or increasing the workflow timeout.

## Timeout and manual batch sizing

The job timeout is 15 minutes. The default attempt limit of `20` is the normal control on scheduled work; the timeout is only the final backstop.

For larger manual batches, increase `limit` carefully. Each place can generate multiple Unsplash requests, and the script pauses between attempted entries. `limit=0` removes the attempt bound, but Unsplash quota and the job timeout still apply, so it should be reserved for deliberate manual runs.

## Files involved

- `.github/workflows/update-place-photos.yml`: Workflow definition.
- `scripts/sync_place_photo_tree.py`: Synchronizes placeholders and prunes stale files safely.
- `scripts/generate_place_photos.py`: Selects candidates, rotates normal runs through the cursor, searches Unsplash, writes photo records, rebuilds the manifest, and updates the version.
- `scripts/photo_queries.py`: Builds deterministic search queries from place IDs and paths.
- `photo_cursor.json`: Stores the last attempted place ID for normal blank-filling runs.
- `manifest.json`: Lists place IDs with complete usable photo records.
- `version.json`: Public payload version incremented when cached photo metadata or the rebuilt manifest changes.

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`photo-selection.md`](photo-selection.md): Candidate ordering, cursor behavior, search queries, Unsplash settings, result selection, no-result, rate-limit, and failure behavior.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
