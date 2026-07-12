# GitHub Actions

## Update Place Photos

The `Update Place Photos` workflow is defined in `.github/workflows/update-place-photos.yml`.

It keeps country, subdivision, and city photo paths synchronized with the private source place tree, searches Unsplash for eligible photos across the public photo tree, advances the normal blank-entry cursor, rebuilds the public manifest, bumps `version.json` when cached photo metadata or the rebuilt manifest changes, and commits any resulting updates. Region membership in `place_photos/world.json` is maintained separately.

## Schedule and manual runs

The workflow runs automatically every three hours at 17 minutes past the hour. It can also be started manually from the GitHub Actions tab.

Manual runs support these inputs:

- `limit`: Maximum number of eligible place entries to attempt. The default is `10`. The value must be `0` or greater, and `0` removes the attempt limit.
- `overwrite`: When `true`, refresh existing photos instead of filling only blank entries. Existing photos are processed from the oldest cached entry first.

The limit counts attempted place entries, not successful photo matches. A place may use more than one Unsplash search query, but it still counts as one attempted entry.

Normal blank-filling runs resume after `photo_cursor.json` and wrap through the deterministic queue. Overwrite runs keep their separate oldest-photo-first order and do not change the cursor.

## Concurrency

All runs use the `update-place-photos` concurrency group, so only one update run executes at a time.

`cancel-in-progress` is disabled. A newly triggered run does not cancel the run already in progress. With the default GitHub Actions queue behavior, at most one additional run remains pending; a newer pending run may replace an older pending run in the same concurrency group.

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
10. Commit and push when photo data, synchronized placeholders, the manifest, the version, or the cursor changed.

## Normal successful outcomes

The following conditions are normal and must complete successfully:

- No eligible photo entries remain.
- The attempted places return no Unsplash results.
- The configured attempt limit is reached without finding a photo.
- Unsplash reports exhausted API quota through HTTP 429 or its recognized HTTP 403 rate-limit response.
- Only `photo_cursor.json` changes.
- The workflow produces no repository changes.

In all of these cases the scripts exit successfully. If no tracked files changed, the commit step reports `no changes to commit`; otherwise it commits the resulting synchronization, generated-data, or cursor changes.

Recognized quota-exhaustion responses are logged as warnings because they use the clean-stop path. Ordinary HTTP 403 responses and other unexpected HTTP responses are logged as errors and fail the run.

## Real failures

The workflow should remain red for problems that require attention, including:

- Missing required secrets.
- Failure to check out the source repository.
- A missing or invalid source path.
- An invalid attempt limit, including a negative value.
- Unsafe stale-file pruning beyond the configured safety threshold.
- A missing `version.json` when photo metadata or manifest changes require a version bump.
- Malformed public photo, manifest, version, or cursor JSON required by the generation step.
- Unexpected Unsplash or network errors other than recognized quota exhaustion.
- A failed Git commit or push.

Malformed source JSON is skipped by the synchronization script and does not fail the workflow by itself.

Do not hide real failures by broadly ignoring command exit codes or increasing the workflow timeout.

## Timeout and attempt limits

The job timeout is 15 minutes. The normal default run attempts only 10 eligible entries, which prevents a long series of unsuccessful searches from running until GitHub cancels the job.

If larger manual batches are needed, increase `limit` carefully while keeping it at `0` or greater. Each city can generate multiple Unsplash requests and the script pauses between attempted entries.

The cursor makes progress persistent between normal runs, so a small limit does not cause the same first entries to block the rest of the queue.

## Files involved

- `.github/workflows/update-place-photos.yml`: Workflow definition.
- `sync_place_photo_tree.py`: Synchronizes placeholders and prunes stale files safely.
- `generate_place_photos.py`: Selects candidates, rotates normal runs through the cursor, searches Unsplash, writes photo records, rebuilds the manifest, and updates the version.
- `photo_queries.py`: Builds deterministic search queries from place IDs and paths.
- `photo_cursor.json`: Stores the last attempted place ID for normal blank-filling runs.
- `manifest.json`: Lists place IDs with complete usable photo records.
- `version.json`: Public payload version incremented when cached photo metadata or the rebuilt manifest changes.

## Related documentation

- [`photo-data.md`](photo-data.md): Public schema, path conventions, manifest rules, version behavior, and attribution requirements.
- [`photo-selection.md`](photo-selection.md): Candidate ordering, cursor behavior, search queries, Unsplash settings, result selection, and retry behavior.
- [`sync-and-cleanup.md`](sync-and-cleanup.md): Source synchronization, cached-photo migration, stale cleanup, and deletion safeguards.
