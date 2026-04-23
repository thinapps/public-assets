# Public Assets 

- `update-place-photos.yml` GitHub Actions workflow for updating cached place photos
- `generate_place_photos.py` main Python script for scanning, fetching, and saving place photo metadata
  - `photo_queries.py` helper Python script for path parsing and Unsplash query generation
- `manifest.json` rebuilt from valid cached place photo entries
- `version.json` bumped only when photo metadata actually changes

### Unsplash Queries
- country: `Country`
- subdivision: `Subdivision Country`
- city: `City Subdivision`
- city fallback: `City Country`
