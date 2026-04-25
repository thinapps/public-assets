# Public Assets 

- `update-place-photos.yml` GitHub Actions workflow for syncing the place photo tree and updating cached place photos
- `sync_place_photo_tree.py` Python script for mirroring missing place photo placeholder files from the private source app repo
- `generate_place_photos.py` main Python script for scanning, fetching, and saving place photo metadata
- `photo_queries.py` helper Python module used by `generate_place_photos.py` for path parsing and Unsplash query generation
- `manifest.json` rebuilt from valid cached place photo entries
- `version.json` bumped only when photo metadata actually changes

### Unsplash Queries
- country: `Country`
- subdivision: `Subdivision Country`
- city: `City Subdivision`
- city fallback: `City Country`
