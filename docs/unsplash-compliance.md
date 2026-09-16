# Unsplash API compliance

This document records the Unsplash-specific behavior used by the Freebase place-photo pipeline and the rules that should be preserved when the integration changes.

The primary reference is the official Unsplash API guidance:

- https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines
- https://help.unsplash.com/en/articles/2511258-guideline-triggering-a-download
- https://help.unsplash.com/en/articles/2511315-guideline-attribution

These requirements can change. Review the current Unsplash documentation before materially changing the photo pipeline.

## Architecture

Unsplash API requests are made by this repository, not by the `freebase.top` website.

`scripts/generate_place_photos.py` searches Unsplash, chooses a photo for a place, and stores only the metadata needed by downstream consumers. `freebase.top` later reads the generated lookup and renders those photos.

The website does not expose an Unsplash API key and does not call the Unsplash API directly.

## Image hotlinking

Do not download Unsplash image files into this repository or copy them to Freebase-controlled storage.

The generator stores the image URL returned by Unsplash in `photo.urls.regular`. Downstream consumers use that `images.unsplash.com` URL directly.

This preserves Unsplash image hotlinking rather than replacing the image with a locally hosted copy.

## Attribution metadata

Each usable photo record must retain:

- `image_url`
- `photographer_name`
- `photographer_url`
- `source_url`

The photographer URL and photo/source URL are derived from the Unsplash API response and include the Freebase referral parameters:

- `utm_source=freebase`
- `utm_medium=referral`

Do not remove these parameters when normalizing or rebuilding photo data.

Downstream interfaces that display an Unsplash photo should keep visible attribution to the photographer and Unsplash, with working links based on this metadata.

## Download-location tracking

Unsplash uses `photo.links.download_location` as a usage-tracking event when an application selects a photo for use. This is not the image URL and does not mean that Freebase downloads or stores the image file.

Whenever the generator selects a photo that will actually be written as a new or changed place-photo assignment, it must make one authenticated request to the returned `links.download_location` URL.

Current behavior is implemented by `trigger_unsplash_download()` in `scripts/generate_place_photos.py`.

The tracking request:

- uses the existing `UNSPLASH_ACCESS_KEY` with `Authorization: Client-ID ...`;
- uses the `download_location` URL supplied by Unsplash without rebuilding or stripping its query string;
- runs only when a changed photo assignment is about to be persisted;
- does not run for a dry run;
- does not run when the selected record produces no change.

The tracking request is intentionally made before the local JSON write. If Unsplash rejects the tracking request, the new assignment is not persisted as though it had been successfully tracked.

Do not trigger `download_location` for ordinary website page views. A visitor viewing a Freebase place page is not a new photo-selection event.

## API-key handling

`UNSPLASH_ACCESS_KEY` is read from the environment at runtime.

For GitHub Actions it is supplied through the repository secret named `UNSPLASH_ACCESS_KEY`.

Never:

- commit the key to this repository;
- put it in generated JSON;
- expose it in `freebase.top` HTML or JavaScript;
- include it in logs or attribution URLs.

## Search and selection

The Unsplash API is used only to find place imagery for Freebase. The resulting experience is a place-information product rather than an Unsplash clone, stock-photo browser, or general photo-download service.

The current generator searches for a place, considers a limited set of results, and chooses one photo for that place. Changes to automated or scheduled selection behavior should be reviewed against the latest Unsplash requirement that API integrations provide authentic, high-quality experiences and any current restrictions on automated API usage.

Do not assume that an existing schedule or historical implementation is permanently permitted simply because the technical API call succeeds.

## Stored data and caching

Freebase may cache the metadata needed to render and attribute a selected photo, including its Unsplash CDN image URL and attribution links.

Do not turn this cache into a mirror of Unsplash image binaries or a general-purpose copy of Unsplash catalog data.

When an existing assignment is refreshed or replaced, treat the newly selected photo as a new usage selection and trigger its `download_location` before persisting the replacement.

## Consumer requirements

Any Freebase surface that consumes this photo dataset should preserve these rules:

1. Render the Unsplash CDN URL rather than copying the image to another image host.
2. Display photographer attribution and an Unsplash/photo-source link.
3. Keep Freebase referral UTM parameters on Unsplash attribution links.
4. Do not expose the Unsplash API key.
5. Do not trigger download tracking on ordinary image views; selection tracking belongs in the generator.

For `freebase.top`, the visible photo attribution is rendered over the image at the bottom-right. Styling can change, but attribution must remain readable and usable.

## Maintenance checklist

Before changing the Unsplash integration, verify that:

- `photo.urls.regular` or another API-provided Unsplash image URL is still used directly;
- photographer name and attribution URLs are still retained;
- referral UTM parameters are still added;
- `links.download_location` is still triggered once for each newly persisted selection;
- dry runs and unchanged records do not create false download events;
- the API key remains secret and server-side;
- current Unsplash API guidelines have been reviewed for changes affecting automation, attribution, caching, or tracking.
