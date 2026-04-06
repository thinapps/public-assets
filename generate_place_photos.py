#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import error, parse, request

# Unsplash api base for search requests.
UNSPLASH_API_BASE = "https://api.unsplash.com"

# Unsplash wants attribution links to include your app/source info.
# These can stay hardcoded, or an admin can override them with repo/env settings later.
UTM_SOURCE = os.environ.get("UNSPLASH_UTM_SOURCE", "freebase")
UTM_MEDIUM = os.environ.get("UNSPLASH_UTM_MEDIUM", "referral")

# Default repo paths.
# This script assumes it lives at the repo root next to version.json and place_photos/.
DEFAULT_ROOT = Path(__file__).resolve().parent
PLACE_PHOTOS_DIR = DEFAULT_ROOT / "place_photos"
VERSION_FILE = DEFAULT_ROOT / "version.json"

# Canonical schema for every place photo object.
# Keeping this centralized makes it easier to backfill blanks consistently.
PHOTO_FIELDS = (
    "place_id",
    "image_url",
    "photographer_name",
    "photographer_url",
    "source_url",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    # Repo root to operate on.
    # Most admins will never change this unless they test against another checkout path.
    parser.add_argument("--root", default=str(DEFAULT_ROOT))

    # Max number of entries to fill in one run.
    # Use 0 for no limit.
    parser.add_argument("--limit", type=int, default=0)

    # Number of Unsplash results to fetch before picking the best one.
    # Higher values can improve quality a bit, but also use more response payload.
    parser.add_argument("--per-page", type=int, default=7)

    # Sleep between successful requests.
    # Helpful for being a little gentler on the api during larger runs.
    parser.add_argument("--pause", type=float, default=1.25)

    # When false, only blank image_url entries are filled.
    # When true, already-populated entries can be replaced.
    parser.add_argument("--overwrite", action="store_true")

    # Preview changes without writing files.
    parser.add_argument("--dry-run", action="store_true")

    # Optional path filter, usually used from the Actions UI.
    parser.add_argument("--path-contains", default="")

    # Optional machine-id filter, usually used from the Actions UI.
    parser.add_argument("--place-id-contains", default="")

    # Optional manual suffix to steer search results.
    # Blank is usually best because the script can choose smarter defaults by place type.
    parser.add_argument("--query-suffix", default="")

    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def slug_to_label(value: str) -> str:
    value = value.strip().replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value.title()


def append_referral(url: str) -> str:
    # Keep blank urls blank instead of generating malformed referral links.
    if not url:
        return ""

    parsed = parse.urlsplit(url)
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in {"utm_source", "utm_medium"}]
    pairs.append(("utm_source", UTM_SOURCE))
    pairs.append(("utm_medium", UTM_MEDIUM))
    query = parse.urlencode(pairs)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def infer_location_from_path(file_path: Path) -> Tuple[str, str]:
    # Infer a human-readable label and a default search suffix from folder structure.
    # This is mainly a fallback helper when place_id parsing is incomplete or awkward.
    rel = file_path.relative_to(PLACE_PHOTOS_DIR)
    parts = rel.parts
    if not parts:
        return ("Location", "travel")

    if parts == ("world.json",):
        return ("World", "travel")

    if parts[0] == "countries":
        country = slug_to_label(parts[1]) if len(parts) > 1 else ""

        # country-level metadata files use names like _japan.json
        if len(parts) == 3 and parts[2].startswith("_"):
            return (country, "travel")

        # subdivision-level metadata files use names like ontario/_ontario.json
        if len(parts) == 4 and parts[3].startswith("_"):
            subdivision = slug_to_label(parts[2])
            return (f"{subdivision}, {country}", "travel")

        # city files should usually search more like a skyline/city photo than generic travel.
        if len(parts) >= 4 and not parts[-1].startswith("_"):
            city = slug_to_label(parts[-1].replace(".json", ""))
            subdivision = slug_to_label(parts[-2])

            # Avoid ugly duplicates like Bangkok, Bangkok, Thailand.
            if city.lower() == subdivision.lower():
                return (f"{city}, {country}", "skyline city")

            return (f"{city}, {subdivision}, {country}", "skyline city")

    return (slug_to_label(file_path.stem), "travel")


def infer_query(place_id: str, file_path: Path, query_suffix: str) -> str:
    # Build the most useful search query we can from place_id first.
    # Then reconcile it with the folder-based label when needed.
    if place_id.startswith("region:"):
        region = slug_to_label(place_id.split(":", 1)[1])
        base = region
    elif place_id.startswith("country:"):
        country = slug_to_label(place_id.split(":", 1)[1])
        base = country
    elif place_id.startswith("subdivision:"):
        parts = place_id.split(":")
        if len(parts) >= 3:
            _, country_slug, subdivision_slug = parts[:3]
            base = f"{slug_to_label(subdivision_slug)}, {slug_to_label(country_slug)}"
        else:
            base, _ = infer_location_from_path(file_path)
    elif place_id.startswith("city:"):
        parts = place_id.split(":")
        if len(parts) >= 4:
            _, country_slug, subdivision_slug, city_slug = parts[:4]
            city = slug_to_label(city_slug)
            subdivision = slug_to_label(subdivision_slug)
            country = slug_to_label(country_slug)

            # Avoid ugly duplicates like Bangkok, Bangkok, Thailand.
            if city.lower() == subdivision.lower():
                base = f"{city}, {country}"
            else:
                base = f"{city}, {subdivision}, {country}"
        else:
            base, _ = infer_location_from_path(file_path)
    else:
        base, _ = infer_location_from_path(file_path)

    path_base, path_suffix = infer_location_from_path(file_path)

    # Prefer the cleaner path-derived label when it disagrees with the raw place_id-derived one.
    # This helps smooth over any awkward machine-id patterns without editing ids.
    if base != path_base:
        base = path_base

    # Manual query_suffix from the workflow wins when provided.
    # Otherwise fall back to the inferred suffix, usually travel or skyline city.
    suffix = query_suffix.strip() or path_suffix
    return f"{base} {suffix}".strip()


def unsplash_get(access_key: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    query = parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    url = f"{UNSPLASH_API_BASE}{endpoint}?{query}"
    req = request.Request(url)
    req.add_header("Authorization", f"Client-ID {access_key}")
    req.add_header("Accept-Version", "v1")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def choose_photo(access_key: str, query: str, per_page: int) -> Dict[str, Any]:
    # Search Unsplash and pick one result.
    # This is intentionally simple and deterministic enough for a beta workflow.
    payload = unsplash_get(
        access_key,
        "/search/photos",
        {
            "query": query,
            "page": 1,
            "per_page": per_page,
            "orientation": "landscape",
            "content_filter": "high",
        },
    )

    results = payload.get("results", [])
    if not results:
        raise RuntimeError(f"no Unsplash results for query: {query}")

    # Prefer larger landscape images first, then use likes as a rough quality tie-breaker.
    candidates = sorted(
        results,
        key=lambda item: (
            int(item.get("width", 0) >= 1600),
            int(item.get("height", 0) >= 900),
            item.get("likes", 0),
        ),
        reverse=True,
    )
    return candidates[0]


def normalize_photo_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    # Preserve place_id but force every object into the canonical 5-field schema.
    # This keeps placeholder files and filled files structurally consistent.
    normalized = {
        "place_id": entry.get("place_id", ""),
        "image_url": entry.get("image_url", ""),
        "photographer_name": entry.get("photographer_name", ""),
        "photographer_url": entry.get("photographer_url", ""),
        "source_url": entry.get("source_url", ""),
    }
    return normalized


def build_photo_entry(existing: Dict[str, Any], photo: Dict[str, Any]) -> Dict[str, Any]:
    # Start from a normalized entry so field order and blanks stay consistent.
    updated = normalize_photo_entry(existing)
    updated.update(
        {
            "image_url": photo.get("urls", {}).get("regular", ""),
            "photographer_name": photo.get("user", {}).get("name", ""),
            "photographer_url": append_referral(photo.get("user", {}).get("links", {}).get("html", "")),
            "source_url": append_referral(photo.get("links", {}).get("html", "")),
        }
    )
    return updated


def should_process(entry: Dict[str, Any], args: argparse.Namespace) -> bool:
    place_id = entry.get("place_id", "")

    # Optional machine-id filter from the workflow.
    if args.place_id_contains and args.place_id_contains.lower() not in place_id.lower():
        return False

    # Safer default behavior is to only fill blank image slots.
    if not args.overwrite and entry.get("image_url"):
        return False

    return True


def iter_photo_files(root: Path) -> List[Path]:
    files = sorted((root / "place_photos").rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


def update_version_file(root: Path, dry_run: bool) -> None:
    # This repo uses a very simple integer version file.
    # Bump it only when at least one file was actually changed.
    version_path = root / "version.json"
    if not version_path.exists():
        return

    payload = load_json(version_path)
    if not isinstance(payload, dict):
        raise RuntimeError("version.json must contain a json object")

    current_version = payload.get("version", 0)
    try:
        current_version = int(current_version)
    except (TypeError, ValueError):
        raise RuntimeError("version.json field 'version' must be an integer")

    payload["version"] = current_version + 1

    if dry_run:
        print(f"would bump {version_path} to version={payload['version']}")
        return

    save_json(version_path, payload)
    print(f"bumped {version_path} to version={payload['version']}")


def main() -> int:
    args = parse_args()
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not access_key:
        print("missing UNSPLASH_ACCESS_KEY", file=sys.stderr)
        return 1

    root = Path(args.root).resolve()
    global PLACE_PHOTOS_DIR
    global VERSION_FILE
    PLACE_PHOTOS_DIR = root / "place_photos"
    VERSION_FILE = root / "version.json"

    processed = 0
    changed_files = 0
    files = iter_photo_files(root)

    for file_path in files:
        rel = file_path.relative_to(root).as_posix()

        # Optional path filter from the workflow, usually the easiest way to target a country subtree.
        if args.path_contains and args.path_contains.lower() not in rel.lower():
            continue

        payload = load_json(file_path)
        if not isinstance(payload, list):
            print(f"skip non-list json: {rel}")
            continue

        file_changed = False
        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                continue

            # Normalize every object we touch so structure stays consistent across the repo.
            normalized_entry = normalize_photo_entry(entry)
            if normalized_entry != entry:
                payload[index] = normalized_entry
                entry = normalized_entry
                file_changed = True
            else:
                entry = normalized_entry

            if not should_process(entry, args):
                continue

            place_id = entry.get("place_id", "")
            if not place_id:
                print(f"skip missing place_id: {rel} [{index}]")
                continue

            query = infer_query(place_id, file_path, args.query_suffix)
            print(f"search {place_id} -> {query}")

            try:
                photo = choose_photo(access_key, query, args.per_page)
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                print(f"http error for {place_id}: {exc.code} {body}", file=sys.stderr)
                return 1
            except Exception as exc:
                # Keep going on per-place failures so one bad query does not kill the whole run.
                print(f"error for {place_id}: {exc}", file=sys.stderr)
                continue

            updated_entry = build_photo_entry(entry, photo)
            if updated_entry != entry:
                payload[index] = updated_entry
                file_changed = True
                processed += 1

            if args.limit and processed >= args.limit:
                break

            if args.pause > 0:
                time.sleep(args.pause)

        if file_changed:
            changed_files += 1
            if args.dry_run:
                print(f"would update {rel}")
            else:
                save_json(file_path, payload)
                print(f"updated {rel}")

        if args.limit and processed >= args.limit:
            break

    if changed_files:
        update_version_file(root, dry_run=args.dry_run)

    print(f"processed_entries={processed} changed_files={changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
