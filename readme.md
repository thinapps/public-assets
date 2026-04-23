# Public Assets 

- `update-place-photos.yml` workflow to call Python script
- `generate_place_photos.py` Python script to retrieve and cache place photos
- `manifest.json` will be updated when new place photos are cached
- `version.json` will be bumped after successful workflow run 

### Unsplash Queries
- country: `Country`
- subdivision: `Subdivision Country`
- city: `City Subdivision`
- city fallback: `City Country`
