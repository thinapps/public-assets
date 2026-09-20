# Unsplash API Compliance

This document records the Unsplash-specific behavior used by the place-photo pipeline and the rules that should be preserved when the integration changes.

The primary reference is the official Unsplash API guidance:

- https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines
- https://help.unsplash.com/en/articles/2511258-guideline-triggering-a-download
- https://help.unsplash.com/en/articles/2511315-guideline-attribution

These requirements can change. Review the current Unsplash documentation before materially changing the photo pipeline.

## Architecture

Unsplash API requests are made by this repository.

`scripts/generate_place_photos.py` searches Unsplash, chooses a photo for a place, and stores only the metadata needed by downstream consumers. Downstream consumers later read the generated data and render those photos.

Consumers do not receive an Unsplash API key and should not call the Unsplash API directly for this dataset.

## Image hotlinking

Do not download Unsplash image files into this repository or copy them to separately controlled storage.

The generator stores the image URL returned by Unsplash in `photo.urls.regular`. Downstream consumers use that `images.unsplash.com` URL directly.

This preserves Unsplash image hotlinking rather than replacing the image with a locally hosted copy.

## Attribution metadata

Each usable photo record must retain:

- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`

The photographer URL and photo/source URL are derived from the Unsplash API response and include the configured referral parameters:

- `utm_source=freebase`
- `utm_medium=referral`

Do not remove these parameters when normalizing or rebuilding photo data.

Downstream interfaces that display an Unsplash photo should keep visible attribution to the photographer and Unsplash, with working links based on this metadata.

## Download-location tracking

Unsplash uses `photo.links.download_location` as a usage-tracking event when an application selects a photo for use. This is not the image URL and does not mean that the image file is downloaded or stored locally.

Whenever the generator selects a photo for a new assignment, a different replacement, or repair of an incomplete record, it must make one authenticated request to the returned `links.download_location` URL before that assignment is persisted.

Current behavior is implemented by `trigger_unsplash_download()` in `scripts/generate_place_photos.py`.

The tracking request:

- uses the existing `UNSPLASH_ACCESS_KEY` with `Authorization: Client-ID ...`;
- uses the `download_location` URL supplied by Unsplash without rebuilding or stripping its query string;
- runs when a new assignment, different replacement, or incomplete-record repair is about to be persisted;
- does not run for a dry run;
- does not run when refresh search reselects the same underlying Unsplash photo for an already-complete record, even when attribution metadata or `cached_at` is refreshed.

For refresh identity checks, the generator compares the stable `images.unsplash.com` host and URL path and ignores query parameters. This prevents API-generated URL parameter changes from being treated as a different image. The existing API-provided image URL is retained when the underlying photo matches.

The tracking request is intentionally made before the local JSON write. If Unsplash rejects the tracking request, the new or repaired assignment is not persisted as though it had been successfully tracked.

Do not trigger `download_location` for ordinary downstream page views. A visitor viewing a rendered place page is not a new photo-selection event.

## API-key handling

`UNSPLASH_ACCESS_KEY` is read from the environment at runtime.

For GitHub Actions it is supplied through the repository secret named `UNSPLASH_ACCESS_KEY`.

Never:

- commit the key to this repository;
- put it in generated JSON;
- expose it in downstream HTML or JavaScript;
- include it in logs or attribution URLs.

## Search and selection

The Unsplash API is used only to find place imagery. The resulting experience is a place-information use case rather than an Unsplash clone, stock-photo browser, or general photo-download service.

The current generator searches for a specific known place, considers a limited set of relevant results, and chooses one photo for that place. API-backed generation is currently manual-only through `workflow_dispatch` so each run is deliberate and bounded.

Historically, the workflow also ran automatically every three hours at 17 minutes past the hour using the cron expression `17 */3 * * *`. That schedule was removed while preparing for Unsplash production API access because Unsplash currently describes its API as intended for non-automated, high-quality, authentic experiences. The previous schedule may be restored later if Unsplash confirms that this specific bounded automated photo-selection workflow is acceptable.

The pipeline remains intentionally narrow and product-specific:

- it enriches an existing place-information use case instead of creating a photo-search or photo-download product;
- it searches only for known places rather than crawling the Unsplash catalog generally;
- it processes bounded batches with rate-limit handling instead of aggressively harvesting API data;
- it stores only the metadata needed to render and attribute one selected image per place;
- it hotlinks Unsplash-hosted images rather than mirroring image files;
- it preserves photographer and Unsplash attribution with referral parameters;
- it triggers Unsplash download-location tracking for new assignments, different selected images, and repairs of incomplete records that are actually persisted;
- it is not used for spam, advertising inventory, AI training, or bulk resale of Unsplash content.

Do not re-enable scheduled API runs merely because the technical API call succeeds. Review the current Unsplash guidance first and, when possible, get confirmation that this automation pattern is permitted before restoring the historical cron schedule.

## Stored data and caching

This repository may cache the metadata needed to render and attribute a selected photo, including its Unsplash CDN image URL and attribution links.

Do not turn this cache into a mirror of Unsplash image binaries or a general-purpose copy of Unsplash catalog data.

When an existing complete assignment is replaced with a different selected photo, treat that replacement as a new usage selection and trigger its `download_location` before persisting it. Repair of an incomplete record also uses normal selection tracking before the complete API-derived assignment is persisted. When refresh search reselects the same underlying photo for an already-complete record, the existing API-provided image URL is retained, attribution metadata may be refreshed, and no new download event is triggered.

## Consumer requirements

Any surface that consumes this photo dataset should preserve these rules:

1. Render the Unsplash CDN URL rather than copying the image to another image host.
2. Display photographer attribution and an Unsplash/photo-source link.
3. Keep the configured referral UTM parameters on Unsplash attribution links.
4. Do not expose the Unsplash API key.
5. Do not trigger download tracking on ordinary image views; selection tracking belongs in the generator.

Styling can vary by consumer, but attribution must remain readable and usable.

## Maintenance checklist

Before changing the Unsplash integration, verify that:

- `photo.urls.regular` or another API-provided Unsplash image URL is still used directly;
- photographer name and attribution URLs are still retained;
- referral UTM parameters are still added;
- `links.download_location` is still triggered once for each new assignment, different image replacement, or incomplete-record repair that is persisted;
- dry runs and same-photo refreshes of already-complete records do not create false download events, including cache or attribution revalidation;
- stable photo identity ignores volatile `images.unsplash.com` query parameters without replacing the API-provided image URL with a non-Unsplash URL;
- the API key remains secret and server-side;
- API-backed workflow execution remains manual-only unless current Unsplash guidance or direct confirmation supports restoring automation;
- current Unsplash API guidelines have been reviewed for changes affecting automation, attribution, caching, or tracking.
