# GitHub Actions

## Update Place Photos

The `Update Place Photos` workflow is defined in `.github/workflows/update-place-photos.yml`.

It keeps the public place photo tree synchronized with the private source place tree, searches Unsplash for missing photos, rebuilds the public manifest, bumps `version.json` when the public payload changes, and commits any resulting updates.

## Schedule and manual runs

The workflow runs automatically every three hours at 17 minutes past the hour. It can also be started manually from the GitHub Actions tab.

Manual runs support these inputs:

- `limit`: Maximum number of eligible place entries to attempt. The default is `10`. A value of `0` removes the attempt limit.
- `overwrite`: When `true`, refresh existing photos instead of filling only blank entries. Existing photos are processed from the oldest cached entry first.

The limit counts attempted place entries, not successful photo matches. A place may use more than one Unsplash search query, but it still counts as one attempted entry.

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
4. Synchronize public photo placeholders with the current source place tree.
5. Migrate usable cached photos when a place path changes and safely prune stale files.
6. Attempt Unsplash searches for eligible places.
7. Rebuild `manifest.json` from complete cached photo records.
8. Bump `version.json` when photo data or the manifest changes.
9. Commit and push only when tracked public assets changed.

## Normal successful outcomes

The following conditions are normal and must complete successfully:

- No eligible photo entries remain.
- The attempted places return no Unsplash results.
- The configured attempt limit is reached without finding a photo.
- Unsplash returns HTTP 429 because the API quota is exhausted.
- The workflow produces no repository changes.

In these cases the scripts log what happened and exit with status `0`. The commit step then reports `no changes to commit` and also exits successfully.

## Real failures

The workflow should remain red for problems that require attention, including:

- Missing required secrets.
- Failure to check out the source repository.
- A missing or invalid source path.
- Unsafe stale-file pruning beyond the configured safety threshold.
- Malformed required JSON data.
- Unexpected Unsplash or network errors other than handled rate limiting.
- A failed Git commit or push.

Do not hide these failures by broadly ignoring command exit codes or increasing the workflow timeout.

## Timeout and attempt limits

The job timeout is 15 minutes. The normal default run attempts only 10 eligible entries, which prevents a long series of unsuccessful searches from running until GitHub cancels the job.

If larger manual batches are needed, increase `limit` carefully. Each city can generate multiple Unsplash requests and the script pauses between attempted entries.

## Files involved

- `.github/workflows/update-place-photos.yml`: Workflow definition.
- `sync_place_photo_tree.py`: Synchronizes placeholders and prunes stale files safely.
- `generate_place_photos.py`: Selects candidates, searches Unsplash, writes photo records, rebuilds the manifest, and updates the version.
- `photo_queries.py`: Builds deterministic search queries from place IDs and paths.
- `manifest.json`: Lists place IDs with complete usable photo records.
- `version.json`: Public payload version incremented when generated output changes.
