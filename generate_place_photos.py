#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from photo_queries import build_search_queries, infer_place_id_from_path
from urllib import error, parse, request

# core paths and limits
DEFAULT_ROOT = Path(__file__).resolve().parent
DEFAULT_LIMIT = 10
DEFAULT_PAUSE_SECONDS = 1.25
PHOTO_CURSOR_FILENAME = "photo_cursor.json"

# unsplash request defaults
UNSPLASH_API_BASE = "https://api.unsplash.com"
DEFAULT_PER_PAGE = 10
DEFAULT_SELECTION_POOL = 5
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
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be 0 or greater")
    return args


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_cached_at(value: Any) -> float:
    # missing, non-string, or invalid timestamps are treated as oldest
    value = clean_string(value)
    if not value:
        return 0.0

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def append_referral(url: Any) -> str:
    # keep unsplash attribution links consistent
    url = clean_string(url)
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
    urls = photo.get("urls", {})
    user = photo.get("user", {})
    links = photo.get("links", {})

    if not isinstance(urls, dict):
        urls = {}
    if not isinstance(user, dict):
        user = {}
    if not isinstance(links, dict):
        links = {}

    user_links = user.get("links", {})
    if not isinstance(user_links, dict):
        user_links = {}

    updated = normalize_photo_entry(existing)
    updated["image_url"] = urls.get("regular", "")
    updated["photographer_name"] = user.get("name", "")
    updated["photographer_url"] = append_referral(user_links.get("html", ""))
    updated["source_url"] = append_referral(links.get("html", ""))
    updated["cached_at"] = utc_now_iso()
    return updated


def is_valid_photo_entry(entry: Dict[str, Any]) -> bool:
    # manifest should only include fully usable cached photo records
    if not isinstance(entry, dict):
        return False

    required_fields = (
        "place_id",
        "image_url",
        "photographer_name",
        "photographer_url",
        "source_url",
    )
    return all(clean_string(entry.get(field, "")) for field in required_fields)


def iter_photo_files(place_photos_dir: Path) -> List[Path]:
    files = sorted(place_photos_dir.rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


def candidate_sort_key(file_path: Path, index: Optional[int]) -> Tuple[str, int]:
    return (file_path.as_posix(), -1 if index is None else index)


def load_photo_cursor(root: Path) -> str:
    cursor_path = root / PHOTO_CURSOR_FILENAME
    if not cursor_path.exists():
        return ""

    payload = load_json(cursor_path)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{PHOTO_CURSOR_FILENAME} must contain a json object")

    last_attempted_place_id = payload.get("last_attempted_place_id", "")
    if not isinstance(last_attempted_place_id, str):
        raise RuntimeError(f"{PHOTO_CURSOR_FILENAME} field 'last_attempted_place_id' must be a string")

    return last_attempted_place_id.strip()


def update_photo_cursor(root: Path, last_attempted_place_id: str, dry_run: bool) -> bool:
    cursor_path = root / PHOTO_CURSOR_FILENAME
    payload = {
        "last_attempted_place_id": last_attempted_place_id,
    }

    if cursor_path.exists() and load_json(cursor_path) == payload:
        print(f"no cursor changes for {cursor_path}")
        return False

    if dry_run:
        print(f"would update {cursor_path} to {last_attempted_place_id}")
        return True

    save_json(cursor_path, payload)
    print(f"updated {cursor_path} to {last_attempted_place_id}")
    return True


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
    if not isinstance(payload, dict):
        raise RuntimeError("Unsplash search response must contain a json object")

    results = payload.get("results", [])
    if not isinstance(results, list):
        raise RuntimeError("Unsplash search response field 'results' must be a list")

    return results


def photo_likes(photo: Dict[str, Any]) -> int:
    likes = photo.get("likes", 0)
    if not isinstance(likes, int) or isinstance(likes, bool):
        return 0
    return max(likes, 0)


def choose_best_photo(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # keep Unsplash relevance meaningful, then prefer likes within the top results
    candidates = [item for item in results[:DEFAULT_SELECTION_POOL] if isinstance(item, dict)]
    if not candidates:
        return None

    return max(
        enumerate(candidates),
        key=lambda ranked: (photo_likes(ranked[1]), -ranked[0]),
    )[1]


def resolve_photo(access_key: str, queries: List[str]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    tried_queries: List[str] = []

    for query in queries:
        tried_queries.append(query)
        results = fetch_unsplash_results(access_key, query)
        photo = choose_best_photo(results)
        if photo:
            return (photo, tried_queries)

    return (None, tried_queries)


def build_candidates(
    place_photos_dir: Path,
    overwrite: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[str, int]]]:
    # blank-first mode fills missing photos
    # overwrite mode refreshes the oldest cached photos first
    blank_candidates: List[Dict[str, Any]] = []
    filled_candidates: List[Dict[str, Any]] = []
    cursor_positions: Dict[str, Tuple[str, int]] = {}

    for file_path in iter_photo_files(place_photos_dir):
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        # empty arrays are valid placeholders and should still be eligible
        if not payload:
            place_id = infer_place_id_from_path(place_photos_dir, file_path)
            if place_id:
                cursor_positions[place_id] = candidate_sort_key(file_path, None)
                if not overwrite:
                    blank_candidates.append({
                        "file_path": file_path,
                        "index": None,
                        "place_id": place_id,
                        "cached_at": "",
                    })
            continue

        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                continue

            normalized_entry = normalize_photo_entry(entry)
            place_id = clean_string(normalized_entry.get("place_id", ""))
            if not place_id:
                place_id = infer_place_id_from_path(place_photos_dir, file_path) or ""
            if not place_id:
                continue

            sort_key = candidate_sort_key(file_path, index)
            cursor_positions[place_id] = sort_key
            image_url = clean_string(normalized_entry.get("image_url", ""))
            candidate = {
                "file_path": file_path,
                "index": index,
                "place_id": place_id,
                "cached_at": clean_string(normalized_entry.get("cached_at", "")),
            }

            if image_url:
                filled_candidates.append(candidate)
            else:
                blank_candidates.append(candidate)

    blank_candidates.sort(
        key=lambda item: candidate_sort_key(item["file_path"], item["index"])
    )
    filled_candidates.sort(
        key=lambda item: (
            parse_cached_at(item["cached_at"]),
            *candidate_sort_key(item["file_path"], item["index"]),
        )
    )

    if overwrite:
        return (filled_candidates, cursor_positions)

    return (blank_candidates, cursor_positions)


def rotate_candidates_after_cursor(
    candidates: List[Dict[str, Any]],
    cursor_positions: Dict[str, Tuple[str, int]],
    last_attempted_place_id: str,
) -> List[Dict[str, Any]]:
    if not candidates or not last_attempted_place_id:
        return candidates

    cursor_key = cursor_positions.get(last_attempted_place_id)
    if cursor_key is None:
        print(
            f"[WARN] cursor place not found: {last_attempted_place_id}; "
            "starting from the beginning"
        )
        return candidates

    after_cursor: List[Dict[str, Any]] = []
    through_cursor: List[Dict[str, Any]] = []

    for candidate in candidates:
        key = candidate_sort_key(candidate["file_path"], candidate["index"])
        if key > cursor_key:
            after_cursor.append(candidate)
        else:
            through_cursor.append(candidate)

    rotated = after_cursor + through_cursor
    if rotated:
        print(
            f"[INFO] resume after {last_attempted_place_id} -> "
            f"{rotated[0]['place_id']}"
        )
    return rotated


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
        place_id = clean_string(entry.get("place_id", ""))
        if not place_id:
            place_id = candidate["place_id"]
            entry["place_id"] = place_id

    place_id = clean_string(entry.get("place_id", ""))
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
        remaining = str((exc.headers or {}).get("X-Ratelimit-Remaining", "")).strip()
        rate_limit_exhausted = exc.code == 429 or (
            exc.code == 403
            and remaining == "0"
            and "rate limit exceeded" in body.lower()
        )
        if rate_limit_exhausted:
            print(
                f"[WARN] Unsplash rate limit reached for {place_id} "
                f"(HTTP {exc.code}); stopping cleanly"
            )
            return (False, True)
        print(f"[ERROR] api failure for {place_id}: {exc.code} {body}", file=sys.stderr)
        raise
    except error.URLError as exc:
        print(f"[ERROR] network failure for {place_id}: {exc}", file=sys.stderr)
        raise

    if not photo:
        print(f"[WARN] no results for {place_id} -> tried: {' | '.join(tried_queries)}")
        return (False, False)

    updated_entry = build_photo_entry(entry, photo)
    if not is_valid_photo_entry(updated_entry):
        raise RuntimeError(f"incomplete photo metadata returned for {place_id}")

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


def update_manifest_file(root: Path, place_photos_dir: Path, dry_run: bool) -> bool:
    # manifest is rebuilt from valid cached photo entries only
    manifest_path = root / "manifest.json"
    place_ids: List[str] = []

    for file_path in iter_photo_files(place_photos_dir):
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        for entry in payload:
            if is_valid_photo_entry(entry):
                place_ids.append(clean_string(entry["place_id"]))

    manifest_payload = {
        "place_ids": sorted(set(place_ids)),
    }

    if manifest_path.exists() and load_json(manifest_path) == manifest_payload:
        print(f"no manifest changes for {manifest_path}")
        return False

    if dry_run:
        print(f"would update {manifest_path} with {len(manifest_payload['place_ids'])} place_ids")
        return True

    save_json(manifest_path, manifest_payload)
    print(f"updated {manifest_path} with {len(manifest_payload['place_ids'])} place_ids")
    return True


def update_version_file(root: Path, dry_run: bool) -> None:
    # bump version whenever the public photo payload changes
    version_path = root / "version.json"
    if not version_path.exists():
        raise FileNotFoundError(f"required version file does not exist: {version_path}")

    payload = load_json(version_path)
    if not isinstance(payload, dict):
        raise RuntimeError("version.json must contain a json object")

    current_version = payload.get("version")
    if not isinstance(current_version, int) or isinstance(current_version, bool):
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
    cursor_changed = False
    last_attempted_place_id = ""
    candidates, cursor_positions = build_candidates(place_photos_dir, overwrite=args.overwrite)

    if not args.overwrite:
        last_attempted_place_id = load_photo_cursor(root)
        candidates = rotate_candidates_after_cursor(
            candidates,
            cursor_positions,
            last_attempted_place_id,
        )

    if not candidates:
        print("[INFO] no eligible photo entries; nothing to do")

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

        if not args.overwrite:
            last_attempted_place_id = candidate["place_id"]

        if changed:
            changed_entries += 1

        if should_stop:
            stop_cleanly = True
            break

        if args.limit and attempted_entries >= args.limit:
            break

        if DEFAULT_PAUSE_SECONDS > 0:
            time.sleep(DEFAULT_PAUSE_SECONDS)

    if not args.overwrite and attempted_entries:
        cursor_changed = update_photo_cursor(
            root,
            last_attempted_place_id,
            dry_run=args.dry_run,
        )

    manifest_changed = update_manifest_file(root, place_photos_dir, dry_run=args.dry_run)

    if changed_entries or manifest_changed:
        update_version_file(root, dry_run=args.dry_run)

    print(
        f"eligible_candidates={len(candidates)} "
        f"attempted_entries={attempted_entries} "
        f"changed_entries={changed_entries} "
        f"manifest_changed={manifest_changed} "
        f"cursor_changed={cursor_changed}"
    )

    if last_attempted_place_id and not args.overwrite:
        print(f"last_attempted_place_id={last_attempted_place_id}")

    if stop_cleanly:
        print("[INFO] stopped cleanly after Unsplash rate limit")
    elif changed_entries == 0 and not manifest_changed:
        print("[INFO] no photo changes found; exiting successfully")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
