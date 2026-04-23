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

# core paths and limits
DEFAULT_ROOT = Path(__file__).resolve().parent
DEFAULT_LIMIT = 10
DEFAULT_PAUSE_SECONDS = 1.25

# unsplash request defaults
UNSPLASH_API_BASE = "https://api.unsplash.com"
DEFAULT_PER_PAGE = 3
DEFAULT_ORIENTATION = "landscape"
DEFAULT_CONTENT_FILTER = "high"

# referral params for attribution links
UTM_SOURCE = os.environ.get("UNSPLASH_UTM_SOURCE", "freebase")
UTM_MEDIUM = os.environ.get("UNSPLASH_UTM_MEDIUM", "referral")


def parse_args() -> argparse.Namespace:
    # keep cli surface minimal for long term maintenance
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_cached_at(value: str) -> float:
    # missing or invalid timestamps are treated as oldest
    value = str(value or "").strip()
    if not value:
        return 0.0

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def slug_to_label(value: str) -> str:
    # convert machine slugs into cleaner search labels
    value = value.strip().replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value.title()


def normalize_query_text(value: str) -> str:
    # keep searches plain and deterministic with no commas or extra spaces
    value = value.replace(",", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def append_referral(url: str) -> str:
    # keep unsplash attribution links consistent
    if not url:
        return ""

    parsed = parse.urlsplit(url)
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in {"utm_source", "utm_medium"}]
    pairs.append(("utm_source", UTM_SOURCE))
    pairs.append(("utm_medium", UTM_MEDIUM))
    query = parse.urlencode(pairs)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def normalize_photo_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    # preserve the repo schema and keep cached_at optional but supported
    return {
        "place_id": entry.get("place_id", ""),
        "image_url": entry.get("image_url", ""),
        "photographer_name": entry.get("photographer_name", ""),
        "photographer_url": entry.get("photographer_url", ""),
        "source_url": entry.get("source_url", ""),
        "cached_at": entry.get("cached_at", ""),
    }


def build_empty_photo_entry(place_id: str) -> Dict[str, Any]:
    # create a stub record for files that currently only contain an empty array
    return normalize_photo_entry({
        "place_id": place_id,
        "image_url": "",
        "photographer_name": "",
        "photographer_url": "",
        "source_url": "",
        "cached_at": "",
    })


def build_photo_entry(existing: Dict[str, Any], photo: Dict[str, Any]) -> Dict[str, Any]:
    # only stamp cached_at when a photo entry is actually written
    updated = normalize_photo_entry(existing)
    updated["image_url"] = photo.get("urls", {}).get("regular", "")
    updated["photographer_name"] = photo.get("user", {}).get("name", "")
    updated["photographer_url"] = append_referral(photo.get("user", {}).get("links", {}).get("html", ""))
    updated["source_url"] = append_referral(photo.get("links", {}).get("html", ""))
    updated["cached_at"] = utc_now_iso()
    return updated


def is_valid_photo_entry(entry: Dict[str, Any]) -> bool:
    # manifest should only include fully usable cached photo records
    if not isinstance(entry, dict):
        return False

    place_id = str(entry.get("place_id", "")).strip()
    image_url = str(entry.get("image_url", "")).strip()
    photographer_name = str(entry.get("photographer_name", "")).strip()
    photographer_url = str(entry.get("photographer_url", "")).strip()
    source_url = str(entry.get("source_url", "")).strip()

    return bool(place_id and image_url and photographer_name and photographer_url and source_url)


def iter_photo_files(place_photos_dir: Path) -> List[Path]:
    files = sorted(place_photos_dir.rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


def infer_place_id_from_path(place_photos_dir: Path, file_path: Path) -> Optional[str]:
    # infer a single place_id from normal country, subdivision, or city file paths
    rel = file_path.relative_to(place_photos_dir)
    parts = rel.parts

    if not parts or parts == ("world.json",):
        return None

    if parts[0] != "countries" or len(parts) < 3:
        return None

    country_slug = parts[1]

    if len(parts) == 3 and parts[2].startswith("_"):
        return f"country:{country_slug}"

    if len(parts) == 4 and parts[3].startswith("_"):
        subdivision_slug = parts[2]
        return f"subdivision:{country_slug}:{subdivision_slug}"

    if len(parts) >= 4 and not parts[-1].startswith("_"):
        subdivision_slug = parts[-2]
        city_slug = file_path.stem
        return f"city:{country_slug}:{subdivision_slug}:{city_slug}"

    return None


def infer_labels_from_path(place_photos_dir: Path, file_path: Path) -> Dict[str, Optional[str]]:
    # use the path as a clean fallback source of truth
    rel = file_path.relative_to(place_photos_dir)
    parts = rel.parts

    labels: Dict[str, Optional[str]] = {
        "place_type": None,
        "region": None,
        "country": None,
        "subdivision": None,
        "city": None,
    }

    if not parts:
        return labels

    if parts == ("world.json",):
        labels["place_type"] = "world"
        return labels

    if parts[0] != "countries":
        return labels

    labels["country"] = slug_to_label(parts[1]) if len(parts) > 1 else None

    if len(parts) == 3 and parts[2].startswith("_"):
        labels["place_type"] = "country"
        return labels

    if len(parts) == 4 and parts[3].startswith("_"):
        labels["place_type"] = "subdivision"
        labels["subdivision"] = slug_to_label(parts[2])
        return labels

    if len(parts) >= 4 and not parts[-1].startswith("_"):
        labels["place_type"] = "city"
        labels["subdivision"] = slug_to_label(parts[-2])
        labels["city"] = slug_to_label(file_path.stem)
        return labels

    return labels


def infer_query_parts(place_photos_dir: Path, place_id: str, file_path: Path) -> Dict[str, Optional[str]]:
    # prefer place_id but trust the path if ids and paths ever disagree
    path_parts = infer_labels_from_path(place_photos_dir, file_path)

    if place_id.startswith("region:"):
        labels = {
            "place_type": "region",
            "region": slug_to_label(place_id.split(":", 1)[1]),
            "country": None,
            "subdivision": None,
            "city": None,
        }
    elif place_id.startswith("country:"):
        labels = {
            "place_type": "country",
            "region": None,
            "country": slug_to_label(place_id.split(":", 1)[1]),
            "subdivision": None,
            "city": None,
        }
    elif place_id.startswith("subdivision:"):
        parts = place_id.split(":")
        if len(parts) < 3:
            return path_parts

        _, country_slug, subdivision_slug = parts[:3]
        labels = {
            "place_type": "subdivision",
            "region": None,
            "country": slug_to_label(country_slug),
            "subdivision": slug_to_label(subdivision_slug),
            "city": None,
        }
    elif place_id.startswith("city:"):
        parts = place_id.split(":")
        if len(parts) < 4:
            return path_parts

        _, country_slug, subdivision_slug, city_slug = parts[:4]
        labels = {
            "place_type": "city",
            "region": None,
            "country": slug_to_label(country_slug),
            "subdivision": slug_to_label(subdivision_slug),
            "city": slug_to_label(city_slug),
        }
    else:
        return path_parts

    if path_parts["place_type"] and labels["place_type"] != path_parts["place_type"]:
        return path_parts

    for key in ("country", "subdivision", "city"):
        path_value = path_parts.get(key)
        label_value = labels.get(key)
        if path_value and label_value and path_value != label_value:
            return path_parts

    return labels


def dedupe_queries(queries: List[str]) -> List[str]:
    # avoid retrying the same query twice
    results: List[str] = []
    seen = set()

    for query in queries:
        query = normalize_query_text(query)
        key = query.lower()
        if query and key not in seen:
            results.append(query)
            seen.add(key)

    return results


def build_search_queries(place_photos_dir: Path, place_id: str, file_path: Path) -> List[str]:
    # keep queries simple and deterministic
    labels = infer_query_parts(place_photos_dir, place_id, file_path)
    place_type = labels.get("place_type")
    region = labels.get("region")
    country = labels.get("country")
    subdivision = labels.get("subdivision")
    city = labels.get("city")

    if place_type == "city" and city and subdivision and country:
        if city.lower() == subdivision.lower():
            return dedupe_queries([f"{city} {country}"])

        return dedupe_queries([
            f"{city} {subdivision}",
            f"{city} {country}",
        ])

    if place_type == "subdivision" and subdivision and country:
        return dedupe_queries([f"{subdivision} {country}"])

    if place_type == "country" and country:
        return dedupe_queries([country])

    if place_type == "region" and region:
        return dedupe_queries([region])

    if city and subdivision:
        return dedupe_queries([f"{city} {subdivision}", f"{city} {country or ''}"])

    if subdivision and country:
        return dedupe_queries([f"{subdivision} {country}"])

    if country:
        return dedupe_queries([country])

    if region:
        return dedupe_queries([region])

    return []


def unsplash_get(access_key: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    query = parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    url = f"{UNSPLASH_API_BASE}{endpoint}?{query}"

    req = request.Request(url)
    req.add_header("Authorization", f"Client-ID {access_key}")
    req.add_header("Accept-Version", "v1")

    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


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


def choose_best_photo(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # prefer larger images, then likes
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


def resolve_photo(access_key: str, queries: List[str]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    tried_queries: List[str] = []

    for query in queries:
        tried_queries.append(query)
        results = fetch_unsplash_results(access_key, query)
        photo = choose_best_photo(results)
        if photo:
            return (photo, tried_queries)

    return (None, tried_queries)


def build_candidates(place_photos_dir: Path, overwrite: bool) -> List[Dict[str, Any]]:
    # blank-first mode fills missing photos
    # overwrite mode refreshes the oldest cached photos first
    blank_candidates: List[Dict[str, Any]] = []
    filled_candidates: List[Dict[str, Any]] = []

    for file_path in iter_photo_files(place_photos_dir):
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        # empty arrays are valid placeholders and should still be eligible
        if not payload and not overwrite:
            place_id = infer_place_id_from_path(place_photos_dir, file_path)
            if place_id:
                blank_candidates.append({
                    "file_path": file_path,
                    "index": None,
                    "place_id": place_id,
                    "has_photo": False,
                    "cached_at": "",
                })
            continue

        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                continue

            normalized_entry = normalize_photo_entry(entry)
            place_id = str(normalized_entry.get("place_id", "")).strip()
            if not place_id:
                place_id = infer_place_id_from_path(place_photos_dir, file_path) or ""
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

    blank_candidates.sort(key=lambda item: (item["file_path"].as_posix(), str(item["index"])))
    filled_candidates.sort(
        key=lambda item: (
            parse_cached_at(item["cached_at"]),
            item["file_path"].as_posix(),
            str(item["index"]),
        )
    )

    if overwrite:
        return filled_candidates

    return blank_candidates


def process_candidate(
    root: Path,
    place_photos_dir: Path,
    candidate: Dict[str, Any],
    access_key: str,
    dry_run: bool,
) -> Tuple[bool, bool]:
    # return changed, should_stop
    file_path = candidate["file_path"]
    index = candidate["index"]
    rel = file_path.relative_to(root).as_posix()

    payload = load_json(file_path)
    if not isinstance(payload, list):
        print(f"[WARN] skip non-list json: {rel}")
        return (False, False)

    # empty placeholder files need a stub record before photo data can be written
    if index is None:
        entry = build_empty_photo_entry(candidate["place_id"])
    else:
        if index >= len(payload) or not isinstance(payload[index], dict):
            print(f"[WARN] skip missing entry: {rel} [{index}]")
            return (False, False)

        entry = normalize_photo_entry(payload[index])
        place_id = str(entry.get("place_id", "")).strip()
        if not place_id:
            place_id = candidate["place_id"]
            entry["place_id"] = place_id

    place_id = str(entry.get("place_id", "")).strip()
    if not place_id:
        print(f"[WARN] skip missing place_id: {rel} [{index}]")
        return (False, False)

    queries = build_search_queries(place_photos_dir, place_id, file_path)
    if not queries:
        print(f"[WARN] skip empty search query: {place_id}")
        return (False, False)

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
        print(f"[INFO] no change for {place_id}")
        return (False, False)

    if index is None:
        payload = [updated_entry]
    else:
        payload[index] = updated_entry

    if dry_run:
        print(f"would update {rel}")
    else:
        save_json(file_path, payload)
        print(f"updated {rel}")

    print(f"[INFO] found photo for {place_id} -> {tried_queries[-1]}")
    return (True, False)


def update_manifest_file(root: Path, place_photos_dir: Path, dry_run: bool) -> None:
    # manifest is rebuilt from valid cached photo entries only
    manifest_path = root / "manifest.json"
    place_ids: List[str] = []

    for file_path in iter_photo_files(place_photos_dir):
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
    # only bump version when at least one photo entry changed
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
    place_photos_dir = root / "place_photos"

    attempted_entries = 0
    changed_entries = 0
    stop_cleanly = False
    candidates = build_candidates(place_photos_dir, overwrite=args.overwrite)

    for candidate in candidates:
        attempted_entries += 1

        try:
            changed, should_stop = process_candidate(
                root=root,
                place_photos_dir=place_photos_dir,
                candidate=candidate,
                access_key=access_key,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            print(f"[ERROR] unexpected failure for {candidate['place_id']}: {exc}", file=sys.stderr)
            return 1

        if changed:
            changed_entries += 1

        if should_stop:
            stop_cleanly = True
            break

        if args.limit and attempted_entries >= args.limit:
            break

        if DEFAULT_PAUSE_SECONDS > 0:
            time.sleep(DEFAULT_PAUSE_SECONDS)

    update_manifest_file(root, place_photos_dir, dry_run=args.dry_run)

    if changed_entries:
        update_version_file(root, dry_run=args.dry_run)

    print(
        f"eligible_candidates={len(candidates)} "
        f"attempted_entries={attempted_entries} "
        f"changed_entries={changed_entries}"
    )

    if stop_cleanly:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
