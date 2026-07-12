# Sync and Cleanup

## Source of truth

The private source place tree is the authority for active country, subdivision, and city paths.

`sync_place_photo_tree.py` mirrors that structure into `place_photos/countries/`. The public repository stores photo metadata for the current source tree but does not define the canonical place hierarchy itself.

## Normal synchronization

The sync script reads every JSON file under the configured source countries directory and maps each relative source path into `place_photos/countries/`.

For each valid source file, it:

- reads the first source object
- accepts `place_id` or the legacy `id` field
- creates a missing public placeholder file
- normalizes the first public entry to the expected fields while preserving any additional entries
- updates the public `place_id` to the current source value
- preserves existing photo and attribution fields when the path remains current

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

Invalid source JSON, missing source objects, and missing IDs do not create or update a public placeholder for that source file. The source path is still counted as expected, so an existing public file at that exact path is not treated as stale during the same sync run.

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
- `cached_at`, only when already present on the stale record

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

## Relationship to manifest and version

The sync script itself manages the file tree. `generate_place_photos.py` subsequently rebuilds `manifest.json` from complete usable photo records.

When cleanup changes the rebuilt manifest, `version.json` is bumped. Cleanup that leaves the manifest unchanged does not trigger a version bump by itself.

Placeholder-only additions or path normalization can be committed without a version bump when usable photo metadata and the manifest remain unchanged.

## Workflow behavior

The scheduled workflow runs synchronization with `--prune-stale` before attempting Unsplash searches.

This order ensures that:

1. current source paths exist in the public tree
2. safely migratable cached photos are preserved
3. obsolete files are removed
4. missing current entries become eligible for photo searches
5. the manifest and version are regenerated from the final tree

A clean sync with no resulting repository changes is a successful workflow outcome.

## Manual maintenance policy

Manual deletion of stale public files should normally be unnecessary.

For ordinary changes:

1. update the private source place tree
2. run or wait for the workflow
3. review any migration and deletion logs
4. let the scripts rebuild the manifest and version as needed

Manual intervention is appropriate only for deliberate repairs that cannot be represented safely through the source tree and existing migration rules.

See also:

- [`photo-data.md`](photo-data.md)
- [`photo-selection.md`](photo-selection.md)
- [`github-actions.md`](github-actions.md)
