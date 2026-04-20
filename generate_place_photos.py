#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

UNSPLASH_API_BASE = "https://api.unsplash.com"
UTM_SOURCE = os.environ.get("UNSPLASH_UTM_SOURCE", "freebase")
UTM_MEDIUM = os.environ.get("UNSPLASH_UTM_MEDIUM", "referral")
DEFAULT_ROOT = Path(__file__).resolve().parent
PLACE_PHOTOS_DIR = DEFAULT_ROOT / "place_photos"
DEFAULT_LIMIT = 10
DEFAULT_PER_PAGE = 3
DEFAULT_PAUSE = 1.25
DEFAULT_ORIENTATION = "landscape"
DEFAULT_CONTENT_FILTER = "high"
DEFAULT_CITY_QUERY_SUFFIX = ""
DEFAULT_SUBDIVISION_QUERY_SUFFIX = "travel"
DEFAULT_COUNTRY_QUERY_SUFFIX = "travel"
DEFAULT_REGION_QUERY_SUFFIX = "travel"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


# convert repo slugs into cleaner search labels
def slug_to_label(value: str) -> str:
    value = value.strip().replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value.title()


# keep referral params consistent on unsplash links
def append_referral(url: str) -> str:
    if not url:
        return ""

    parsed = parse.urlsplit(url)
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in {"utm_source", "utm_medium"}]
    pairs.append(("utm_source", UTM_SOURCE))
    pairs.append(("utm_medium", UTM_MEDIUM))
    query = parse.urlencode(pairs)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


# infer clean labels from the file path as a fallback source of truth
def infer_location_from_path(file_path: Path) -> Tuple[str, Optional[str], Optional[str]]:
    rel = file_path.relative_to(PLACE_PHOTOS_DIR)
    parts = rel.parts
    if not parts:
        return ("Location", None, None)

    if parts == ("world.json",):
        return ("World", None, None)

    if parts[0] == "countries":
        country = slug_to_label(parts[1]) if len(parts) > 1 else None

        if len(parts) == 3 and parts[2].startswith("_"):
            return (country or "Location", None, country)

        if len(parts) == 4 and parts[3].startswith("_"):
            subdivision = slug_to_label(parts[2])
            return (f"{subdivision}, {country}", subdivision, country)

        if len(parts) >= 4 and not parts[-1].startswith("_"):
            city = slug_to_label(parts[-1].replace(".json", ""))
            subdivision = slug_to_label(parts[-2])

            if city.lower() == subdivision.lower():
                return (f"{city}, {country}", city, country)

            return (f"{city}, {subdivision}, {country}", city, subdivision)

    return (slug_to_label(file_path.stem), None, None)


# prefer place_id, but fall back to the path if ids and paths ever disagree
def infer_query_parts(place_id: str, file_path: Path) -> Tuple[str, Optional[str], Optional[str]]:
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
    if base != path_base:
        return (path_base, path_part_one, path_part_two)

    return (base, part_one, part_two)


def add_suffix(query: str, suffix: str) -> str:
    query = query.strip().strip(",")
    suffix = suffix.strip()
    if suffix:
        return f"{query} {suffix}".strip()
    return query


# avoid retrying the same query string twice
def dedupe_queries(queries: List[str]) -> List[str]:
    normalized_queries: List[str] = []
    seen = set()

    for query in queries:
        query = query.strip().strip(",")
        key = query.lower()
        if query and key not in seen:
            normalized_queries.append(query)
            seen.add(key)

    return normalized_queries


# keep search logic simple and place-type aware
def build_search_queries(place_id: str, file_path: Path) -> List[str]:
    base, part_one, part_two = infer_query_parts(place_id, file_path)

    if place_id.startswith("city:") and part_one and part_two:
        queries = [base, f"{part_one}, {part_two}"]
        parts = [part.strip() for part in base.split(",") if part.strip()]
        if len(parts) >= 2:
            country = parts[-1]
            if country.lower() != part_two.lower():
                queries.append(f"{part_one}, {country}")

        if DEFAULT_CITY_QUERY_SUFFIX:
            queries.append(add_suffix(base, DEFAULT_CITY_QUERY_SUFFIX))

        return dedupe_queries(queries)

    if place_id.startswith("subdivision:"):
        return dedupe_queries([
            base,
            add_suffix(base, DEFAULT_SUBDIVISION_QUERY_SUFFIX),
        ])

    if place_id.startswith("country:"):
        return dedupe_queries([
            base,
            add_suffix(base, DEFAULT_COUNTRY_QUERY_SUFFIX),
        ])

    if place_id.startswith("region:"):
        return dedupe_queries([
            base,
            add_suffix(base, DEFAULT_REGION_QUERY_SUFFIX),
        ])

    return dedupe_queries([base])


def unsplash_get(access_key: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    query = parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    url = f"{UNSPLASH_API_BASE}{endpoint}?{query}"
    req = request.Request(url)
    req.add_header("Authorization", f"Client-ID {access_key}")
    req.add_header("Accept-Version", "v1")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# fetch a small candidate set to keep api usage light
def fetch_unsplash_results(access_key: str, query: str) -> List[Dict[str, Any]]:
    payload = unsplash_get(
        access_key,
        "/search/photos",
        {
            "query": query,
            "page": 1,
            "per_page": DEFAULT_PER_PAGE,
            "orientation": DEFAULT_ORIENTATION,
            "content_filter": DEFAULT_CONTENT_FILTER,
        },
    )
    return payload.get("results", [])


# prefer larger images, then likes, for a stable best pick
def choose_best_photo(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not results:
        return None

    candidates = sorted(
        results,
        key=lambda item: (
            int(item.get("width", 0) * item.get("height", 0)),
            item.get("likes", 0),
        ),
        reverse=True,
    )
    return candidates[0]


# try queries in order until one returns a usable photo
def resolve_photo(access_key: str, queries: List[str]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    tried_queries: List[str] = []

    for query in queries:
        tried_queries.append(query)
        results = fetch_unsplash_results(access_key, query)
        photo = choose_best_photo(results)
        if photo:
            return (photo, tried_queries)

    return (None, tried_queries)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# parse timestamps so overwrite mode can refresh oldest items first
def parse_cached_at(value: str) -> float:
    value = str(value or "").strip()
    if not value:
        return 0.0

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# normalize entry keys so every file follows the same schema

def normalize_photo_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "place_id": entry.get("place_id", ""),
        "image_url": entry.get("image_url", ""),
        "photographer_name": entry.get("photographer_name", ""),
        "photographer_url": entry.get("photographer_url", ""),
        "source_url": entry.get("source_url", ""),
        "cached_at": entry.get("cached_at", ""),
    }
    return normalized


# keep old place_id and only refresh the photo-specific fields
def build_photo_entry(existing: Dict[str, Any], photo: Dict[str, Any]) -> Dict[str, Any]:
    updated = normalize_photo_entry(existing)
    updated.update(
        {
            "image_url": photo.get("urls", {}).get("regular", ""),
            "photographer_name": photo.get("user", {}).get("name", ""),
            "photographer_url": append_referral(photo.get("user", {}).get("links", {}).get("html", "")),
            "source_url": append_referral(photo.get("links", {}).get("html", "")),
            "cached_at": utc_now_iso(),
        }
    )
    return updated


# only photo-backed entries belong in manifest.json
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


# scan the whole tree every run so behavior stays automatic
def iter_photo_files(root: Path) -> List[Path]:
    files = sorted((root / "place_photos").rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


# rebuild manifest from the current valid cached photo entries
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


# only bump version when actual repo content changed
def update_version_file(root: Path, dry_run: bool) -> None:
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


# normalize every json file before processing so the schema stays stable
def normalize_all_files(root: Path, dry_run: bool) -> int:
    changed_files = 0

    for file_path in iter_photo_files(root):
        rel = file_path.relative_to(root).as_posix()
        payload = load_json(file_path)
        if not isinstance(payload, list):
            print(f"[WARN] skip non-list json: {rel}")
            continue

        normalized_payload = []
        file_changed = False

        for entry in payload:
            if not isinstance(entry, dict):
                normalized_payload.append(entry)
                continue

            normalized_entry = normalize_photo_entry(entry)
            normalized_payload.append(normalized_entry)
            if normalized_entry != entry:
                file_changed = True

        if file_changed:
            changed_files += 1
            if dry_run:
                print(f"would normalize {rel}")
            else:
                save_json(file_path, normalized_payload)
                print(f"normalized {rel}")

    return changed_files


# build a deterministic queue of blanks or oldest cached entries
def build_candidates(root: Path, overwrite: bool) -> List[Dict[str, Any]]:
    blank_candidates: List[Dict[str, Any]] = []
    filled_candidates: List[Dict[str, Any]] = []

    for file_path in iter_photo_files(root):
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                continue

            normalized_entry = normalize_photo_entry(entry)
            place_id = str(normalized_entry.get("place_id", "")).strip()
            if not place_id:
                continue

            image_url = str(normalized_entry.get("image_url", "")).strip()
            candidate = {
                "file_path": file_path,
                "index": index,
                "place_id": place_id,
                "has_photo": bool(image_url),
                "cached_at": str(normalized_entry.get("cached_at", "")).strip(),
            }

            if image_url:
                filled_candidates.append(candidate)
            else:
                blank_candidates.append(candidate)

    blank_candidates.sort(key=lambda item: (item["file_path"].as_posix(), item["index"]))
    filled_candidates.sort(key=lambda item: (parse_cached_at(item["cached_at"]), item["file_path"].as_posix(), item["index"]))

    if overwrite:
        return filled_candidates + blank_candidates

    return blank_candidates


# process one entry and stop only on hard api rate limiting
def process_candidate(root: Path, candidate: Dict[str, Any], access_key: str, dry_run: bool) -> Tuple[bool, bool]:
    file_path = candidate["file_path"]
    index = candidate["index"]
    rel = file_path.relative_to(root).as_posix()
    payload = load_json(file_path)
    if not isinstance(payload, list):
        print(f"[WARN] skip non-list json: {rel}")
        return (False, False)

    if index >= len(payload) or not isinstance(payload[index], dict):
        print(f"[WARN] skip missing entry: {rel} [{index}]")
        return (False, False)

    entry = normalize_photo_entry(payload[index])
    place_id = entry.get("place_id", "")
    if not place_id:
        print(f"[WARN] skip missing place_id: {rel} [{index}]")
        return (False, False)

    queries = build_search_queries(place_id, file_path)
    print(f"[INFO] search {place_id} -> {' | '.join(queries)}")

    try:
        photo, tried_queries = resolve_photo(access_key, queries)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[ERROR] api failure for {place_id}: {exc.code} {body}", file=sys.stderr)
        if exc.code == 429:
            return (False, True)
        raise
    except error.URLError as exc:
        print(f"[ERROR] network failure for {place_id}: {exc}", file=sys.stderr)
        raise

    if not photo:
        print(f"[WARN] no results for {place_id} -> tried: {' | '.join(tried_queries)}")
        return (False, False)

    updated_entry = build_photo_entry(entry, photo)
    if updated_entry == entry:
        return (False, False)

    payload[index] = updated_entry

    if dry_run:
        print(f"would update {rel}")
    else:
        save_json(file_path, payload)
        print(f"updated {rel}")

    print(f"[INFO] found photo for {place_id} -> {tried_queries[-1]}")
    return (True, False)


def main() -> int:
    args = parse_args()
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not access_key:
        print("missing UNSPLASH_ACCESS_KEY", file=sys.stderr)
        return 1

    root = Path(args.root).resolve()
    global PLACE_PHOTOS_DIR
    PLACE_PHOTOS_DIR = root / "place_photos"

    changed_files = normalize_all_files(root, dry_run=args.dry_run)
    processed = 0
    stop_cleanly = False
    candidates = build_candidates(root, overwrite=args.overwrite)

    for candidate in candidates:
        try:
            changed, should_stop = process_candidate(root, candidate, access_key, args.dry_run)
        except Exception as exc:
            print(f"[ERROR] unexpected failure for {candidate['place_id']}: {exc}", file=sys.stderr)
            return 1

        if changed:
            changed_files += 1
            processed += 1
            if DEFAULT_PAUSE > 0:
                time.sleep(DEFAULT_PAUSE)

        if should_stop:
            stop_cleanly = True
            break

        if args.limit and processed >= args.limit:
            break

    update_manifest_file(root, dry_run=args.dry_run)

    if changed_files:
        update_version_file(root, dry_run=args.dry_run)

    print(f"eligible_candidates={len(candidates)} processed_entries={processed} changed_files={changed_files}")

    if stop_cleanly:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
