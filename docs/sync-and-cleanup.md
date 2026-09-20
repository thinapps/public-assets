# Sync and Cleanup

## Source of truth

The private source place tree is the authority for active country, subdivision, and city paths.

`scripts/sync_place_photo_tree.py` mirrors that structure into `place_photos/countries/`. The public repository stores photo metadata for the current source tree but does not define the canonical place hierarchy itself.

## Normal synchronization

The sync script reads every JSON file under the configured source countries directory and maps each relative source path into `place_photos/countries/`.

For each valid source file, it:

- reads the first source object
- prefers a valid non-empty string `place_id` and falls back to the legacy `id` field when `place_id` is missing, empty, or not a string
- creates a missing public placeholder file
- normalizes the first public entry to the expected fields while preserving any additional entries
- updates the public `place_id` to the current source value
- preserves existing string photo and attribution fields when the path remains current
- converts non-string public photo metadata values to empty strings so malformed values become incomplete records instead of being treated as usable data
- converts a recoverable public JSON object into the canonical array form while preserving its string photo metadata
- resets valid-but-structurally unusable public JSON, such as a scalar value or a first array entry that is not an object, to a canonical blank first record so normal generation can recover it

A new placeholder uses this shape:

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

Syntactically malformed or unreadable source JSON, missing source objects, and source records without a valid `place_id` or legacy `id` do not create or update a public placeholder for that source file. The source path is still counted as expected, so an existing public file at that exact path is not treated as stale during the same sync run.

Syntactically malformed or unreadable existing public JSON is also left untouched rather than overwritten automatically. Structurally invalid but syntactically valid JSON can be normalized safely because the source tree supplies the canonical place ID and unusable structures contain no trusted photo record to preserve.

Normalization can leave an existing non-empty `image_url` alongside missing or invalid required attribution metadata. Such a record is incomplete rather than usable. The photo generator treats it as a repair candidate, searches the place again, and replaces it with a complete API-derived assignment when a usable result is found.

## Stale-file cleanup

When called with `--prune-stale`, the script identifies public JSON files under `place_photos/countries/` that no longer have a matching source path.

Cleanup only targets that country photo tree. It does not directly prune:

- `place_photos/world.json`
- scripts
- workflows
- documentation
- `manifest.json`
- `version.json`

After stale files are removed, empty directories are removed from the deepest level upward.

## Cached-photo migration

Before deleting a stale public file, the script attempts a conservative migration to a current canonical file.

Automatic migration excludes leading-underscore country and subdivision self files. It normally applies only to city photo files that share the same country and filename after a path change.

A migration occurs only when all of these conditions are true:

- the stale file has a complete usable cached photo record
- a current file has the same country and filename
- exactly one current canonical file matches
- the canonical file does not already contain a complete cached photo
- both stale and canonical payloads are valid non-empty JSON arrays

When these checks pass, the script copies these fields into the canonical record:

- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`
- `cached_at`, only when it is already a non-empty string on the stale record

The canonical `place_id` remains the one produced by the current source tree.

If the replacement is ambiguous, the stale record is incomplete, or the canonical file already has a photo, no migration occurs. The stale file is still removed because it no longer belongs to the current source tree.

## Prune safety guards

Stale cleanup fails instead of deleting files when the cleanup scope appears unsafe.

The script refuses to prune when:

- the source tree produces no expected JSON files
- the current public country photo tree contains no JSON files
- more than 10% of current public country photo JSON files would be deleted in one run

The deletion limit is calculated from the current public file count and always permits at least one stale deletion.

The 10% threshold is intentionally conservative. It permits normal small cleanup batches while blocking likely configuration errors such as:

- a wrong `SOURCE_PLACES_PATH`
- an incomplete or failed source checkout
- an unexpectedly empty source subtree
- a large accidental restructuring

Do not bypass this guard casually. Large intentional source-tree changes should be reviewed and migrated in smaller controlled stages or accompanied by a deliberate code and policy change.

## Relationship to manifest, lookup, and version

The sync script itself manages the file tree. `scripts/generate_place_photos.py` subsequently repairs incomplete records, fills blank placeholders, refreshes older complete assignments when run capacity remains, and rebuilds `manifest.json` from complete usable photo records. The workflow then rebuilds `photos.json` from the same canonical tree.

When synchronization or cleanup changes usable public photo output, the corresponding public version must change. Photo repairs, new assignments, changed refreshed assignments, or manifest changes are handled during generation. A refresh that reselects the same public photo metadata updates only `cached_at` and does not bump the public version. If rebuilding `photos.json` produces a lookup-only change and `version.json` did not already change in the same run, the workflow bumps the version once after the lookup rebuild.

Placeholder-only additions, structural normalization, path normalization, cleanup of invalid metadata, cache-only `cached_at` refreshes, or cursor-only workflow progress can be committed without a version bump when they do not change usable public photo output.

## Workflow behavior

The manual workflow runs synchronization with `--prune-stale` before attempting Unsplash searches.

This order ensures that:

1. current valid source paths exist in the public tree
2. recoverable valid-JSON structural problems are normalized into canonical photo records
3. safely migratable cached photos are preserved
4. obsolete files are removed
5. incomplete existing records become repair candidates and blank or malformed image entries become fill candidates
6. any remaining attempt capacity can refresh complete cached photos from oldest to newest
7. the manifest is rebuilt from the final tree
8. the bulk lookup is rebuilt from the same canonical records
9. `version.json` is bumped when public photo output changes, including lookup-only changes not already covered during generation

A clean sync with no resulting repository changes is a successful workflow outcome.

## Manual maintenance policy

Manual deletion of stale public files should normally be unnecessary.

For ordinary changes:

1. update the private source place tree
2. run the workflow
3. review any normalization, migration, and deletion logs
4. let the workflow repair incomplete photo records, refresh older complete assignments when capacity remains, and rebuild the manifest, lookup, and version as needed

Manual intervention is appropriate only for deliberate repairs that cannot be represented safely through the source tree and existing migration rules.

See also:

- [`photo-data.md`](photo-data.md)
- [`photo-selection.md`](photo-selection.md)
- [`github-actions.md`](github-actions.md)
