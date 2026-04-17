#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

# unsplash api base for search requests
UNSPLASH_API_BASE = "https://api.unsplash.com"

# unsplash wants attribution links to include your app or source info
# these can stay hardcoded, or an admin can override them with env settings later
UTM_SOURCE = os.environ.get("UNSPLASH_UTM_SOURCE", "freebase")
UTM_MEDIUM = os.environ.get("UNSPLASH_UTM_MEDIUM", "referral")

# default repo paths
# this script assumes it lives at the repo root next to version.json and place_photos
DEFAULT_ROOT = Path(__file__).resolve().parent
PLACE_PHOTOS_DIR = DEFAULT_ROOT / "place_photos"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    # repo root to operate on
    # most admins will never change this unless they test against another checkout path
    parser.add_argument("--root", default=str(DEFAULT_ROOT))

    # max number of entries to fill in one run
    # use 0 for no limit
    parser.add_argument("--limit", type=int, default=10)

    # number of unsplash results to fetch before picking the best one
    # keep this low so the script stays lightweight while still allowing simple tie-breaking
    parser.add_argument("--per-page", type=int, default=3)

    # sleep between successful requests
    # helpful for being a little gentler on the api during larger runs
    parser.add_argument("--pause", type=float, default=1.25)

    # when false, only blank image_url entries are filled
    # when true, already-populated entries can be replaced
    parser.add_argument("--overwrite", action="store_true")

    # preview changes without writing files
    parser.add_argument("--dry-run", action="store_true")

    # optional path filter, usually used from the actions ui
    parser.add_argument("--path-contains", default="")

    # optional machine-id filter, usually used from the actions ui
    parser.add_argument("--place-id-contains", default="")

    # optional manual suffix to steer search results
    # blank is usually best because the script now uses structured fallback queries by default
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
    # keep blank urls blank instead of generating malformed referral links
    if not url:
        return ""

    parsed = parse.urlsplit(url)
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in {"utm_source", "utm_medium"}]
    pairs.append(("utm_source", UTM_SOURCE))
    pairs.append(("utm_medium", UTM_MEDIUM))
    query = parse.urlencode(pairs)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def infer_location_from_path(file_path: Path) -> Tuple[str, Optional[str], Optional[str]]:
    # infer clean display/query labels from folder structure
    # this is used only for query building, not for changing machine ids or file paths
    rel = file_path.relative_to(PLACE_PHOTOS_DIR)
    parts = rel.parts
    if not parts:
        return ("Location", None, None)

    if parts == ("world.json",):
        return ("World", None, None)

    if parts[0] == "countries":
        country = slug_to_label(parts[1]) if len(parts) > 1 else None

        # country-level metadata files use names like _japan.json
        if len(parts) == 3 and parts[2].startswith("_"):
            return (country or "Location", None, country)

        # subdivision-level metadata files use names like ontario/_ontario.json
        if len(parts) == 4 and parts[3].startswith("_"):
            subdivision = slug_to_label(parts[2])
            return (f"{subdivision}, {country}", subdivision, country)

        # city files use names like ontario/toronto.json
        if len(parts) >= 4 and not parts[-1].startswith("_"):
            city = slug_to_label(parts[-1].replace(".json", ""))
            subdivision = slug_to_label(parts[-2])

            if city.lower() == subdivision.lower():
                return (f"{city}, {country}", city, country)

            return (f"{city}, {subdivision}, {country}", city, subdivision)

    return (slug_to_label(file_path.stem), None, None)


def infer_query_parts(place_id: str, file_path: Path) -> Tuple[str, Optional[str], Optional[str]]:
    # build the cleanest base labels we can from place_id first
    # then reconcile with path-derived labels when needed
    if place_id.startswith("region:"):
        region = slug_to_label(place_id.split(":", 1)[1])
        base = region
        part_one = region
        part_two = None
    elif place_id.startswith("country:"):
        country = slug_to_label(place_id.split(":", 1)[1])
        base = country
        part_one = None
        part_two = country
    elif place_id.startswith("subdivision:"):
        parts = place_id.split(":")
        if len(parts) >= 3:
            _, country_slug, subdivision_slug = parts[:3]
            subdivision = slug_to_label(subdivision_slug)
            country = slug_to_label(country_slug)
            base = f"{subdivision}, {country}"
            part_one = subdivision
            part_two = country
        else:
            return infer_location_from_path(file_path)
    elif place_id.startswith("city:"):
        parts = place_id.split(":")
        if len(parts) >= 4:
            _, country_slug, subdivision_slug, city_slug = parts[:4]
            city = slug_to_label(city_slug)
            subdivision = slug_to_label(subdivision_slug)
            country = slug_to_label(country_slug)

            if city.lower() == subdivision.lower():
                base = f"{city}, {country}"
                part_one = city
                part_two = country
            else:
                base = f"{city}, {subdivision}, {country}"
                part_one = city
                part_two = subdivision
        else:
            return infer_location_from_path(file_path)
    else:
        return infer_location_from_path(file_path)

    path_base, path_part_one, path_part_two = infer_location_from_path(file_path)

    # prefer the cleaner path-derived label when it disagrees with the raw place_id-derived one
    # this helps smooth over awkward machine-id patterns without editing ids
    if base != path_base:
        return (path_base, path_part_one, path_part_two)

    return (base, part_one, part_two)


def build_search_queries(place_id: str, file_path: Path, query_suffix: str) -> List[str]:
    base, part_one, part_two = infer_query_parts(place_id, file_path)
    suffix = query_suffix.strip()

    queries: List[str] = []

    if place_id.startswith("city:") and part_one and part_two:
        country = None
        parts = [part.strip() for part in base.split(",") if part.strip()]
        if len(parts) >= 2:
            country = parts[-1]

        queries.append(base)
        queries.append(f"{part_one}, {part_two}")

        if country and country.lower() != part_two.lower():
            queries.append(f"{part_one}, {country}")
    else:
        queries.append(base)

    normalized_queries: List[str] = []
    seen = set()

    for query in queries:
        query = query.strip().strip(",")
        if suffix:
            query = f"{query} {suffix}".strip()

        key = query.lower()
        if query and key not in seen:
            normalized_queries.append(query)
            seen.add(key)

    return normalized_queries


def unsplash_get(access_key: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # make one unsplash api request and return the decoded json response
    query = parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    url = f"{UNSPLASH_API_BASE}{endpoint}?{query}"
    req = request.Request(url)
    req.add_header("Authorization", f"Client-ID {access_key}")
    req.add_header("Accept-Version", "v1")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_unsplash_results(access_key: str, query: str, per_page: int) -> List[Dict[str, Any]]:
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
    return payload.get("results", [])


def choose_best_photo(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not results:
        return None

    # prefer larger images first, then use likes as a rough quality tie-breaker
    candidates = sorted(
        results,
        key=lambda item: (
            int(item.get("width", 0) * item.get("height", 0)),
            item.get("likes", 0),
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_photo(access_key: str, queries: List[str], per_page: int) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    tried_queries: List[str] = []

    for query in queries:
        tried_queries.append(query)
        results = fetch_unsplash_results(access_key, query, per_page)
        photo = choose_best_photo(results)
        if photo:
            return (photo, tried_queries)

    return (None, tried_queries)


def normalize_photo_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    # preserve place_id but force every object into the canonical 5-field schema
    # this keeps placeholder files and filled files structurally consistent
    normalized = {
        "place_id": entry.get("place_id", ""),
        "image_url": entry.get("image_url", ""),
        "photographer_name": entry.get("photographer_name", ""),
        "photographer_url": entry.get("photographer_url", ""),
        "source_url": entry.get("source_url", ""),
    }
    return normalized


def build_photo_entry(existing: Dict[str, Any], photo: Dict[str, Any]) -> Dict[str, Any]:
    # start from a normalized entry so field order and blanks stay consistent
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

    # optional machine-id filter from the workflow
    if args.place_id_contains and args.place_id_contains.lower() not in place_id.lower():
        return False

    # safer default behavior is to only fill blank image slots
    if not args.overwrite and entry.get("image_url"):
        return False

    return True


def iter_photo_files(root: Path) -> List[Path]:
    files = sorted((root / "place_photos").rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


def is_valid_photo_entry(entry: Dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False

    place_id = str(entry.get("place_id", "")).strip()
    image_url = str(entry.get("image_url", "")).strip()
    photographer_name = str(entry.get("photographer_name", "")).strip()
    photographer_url = str(entry.get("photographer_url", "")).strip()
    source_url = str(entry.get("source_url", "")).strip()

    if not place_id:
        return False

    if not image_url:
        return False

    if not photographer_name:
        return False

    if not photographer_url:
        return False

    if not source_url:
        return False

    return True


def update_manifest_file(root: Path, dry_run: bool) -> None:
    manifest_path = root / "manifest.json"
    place_ids = []

    for file_path in iter_photo_files(root):
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        for entry in payload:
            if is_valid_photo_entry(entry):
                place_ids.append(entry["place_id"])

    manifest_payload = {
        "place_ids": sorted(set(place_ids)),
    }

    if dry_run:
        print(f"would update {manifest_path} with {len(manifest_payload['place_ids'])} place_ids")
        return

    save_json(manifest_path, manifest_payload)
    print(f"updated {manifest_path} with {len(manifest_payload['place_ids'])} place_ids")


def update_version_file(root: Path, dry_run: bool) -> None:
    # this repo uses a very simple integer version file
    # bump it only when at least one file was actually changed
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

    # repo secret must be present before any api work can happen
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not access_key:
        print("missing UNSPLASH_ACCESS_KEY", file=sys.stderr)
        return 1

    root = Path(args.root).resolve()
    global PLACE_PHOTOS_DIR
    PLACE_PHOTOS_DIR = root / "place_photos"

    processed = 0
    changed_files = 0
    files = iter_photo_files(root)

    for file_path in files:
        rel = file_path.relative_to(root).as_posix()

        # optional path filter from the workflow, usually the easiest way to target a country subtree
        if args.path_contains and args.path_contains.lower() not in rel.lower():
            continue

        payload = load_json(file_path)
        if not isinstance(payload, list):
            print(f"[WARN] skip non-list json: {rel}")
            continue

        file_changed = False
        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                continue

            # normalize every object we touch so structure stays consistent across the repo
            normalized_entry = normalize_photo_entry(entry)
            if normalized_entry != entry:
                payload[index] = normalized_entry
                file_changed = True
            entry = normalized_entry

            if not should_process(entry, args):
                continue

            place_id = entry.get("place_id", "")
            if not place_id:
                print(f"[WARN] skip missing place_id: {rel} [{index}]")
                continue

            queries = build_search_queries(place_id, file_path, args.query_suffix)
            print(f"[INFO] search {place_id} -> {' | '.join(queries)}")

            try:
                photo, tried_queries = resolve_photo(access_key, queries, args.per_page)
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                print(f"[ERROR] api failure for {place_id}: {exc.code} {body}", file=sys.stderr)
                if exc.code == 429:
                    return 0
                return 1
            except error.URLError as exc:
                print(f"[ERROR] network failure for {place_id}: {exc}", file=sys.stderr)
                return 1
            except Exception as exc:
                print(f"[ERROR] unexpected failure for {place_id}: {exc}", file=sys.stderr)
                return 1

            if not photo:
                print(f"[WARN] no results for {place_id} -> tried: {' | '.join(tried_queries)}")
                continue

            updated_entry = build_photo_entry(entry, photo)
            if updated_entry != entry:
                payload[index] = updated_entry
                file_changed = True
                processed += 1
                print(f"[INFO] found photo for {place_id} -> {tried_queries[-1]}")

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

    update_manifest_file(root, dry_run=args.dry_run)

    if changed_files:
        update_version_file(root, dry_run=args.dry_run)

    print(f"processed_entries={processed} changed_files={changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
