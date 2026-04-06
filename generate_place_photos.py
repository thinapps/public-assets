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

UNSPLASH_API_BASE = "https://api.unsplash.com"
UTM_SOURCE = os.environ.get("UNSPLASH_UTM_SOURCE", "freebase")
UTM_MEDIUM = os.environ.get("UNSPLASH_UTM_MEDIUM", "referral")
DEFAULT_ROOT = Path(__file__).resolve().parent
PLACE_PHOTOS_DIR = DEFAULT_ROOT / "place_photos"
VERSION_FILE = DEFAULT_ROOT / "version.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--per-page", type=int, default=7)
    parser.add_argument("--pause", type=float, default=1.25)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--path-contains", default="")
    parser.add_argument("--place-id-contains", default="")
    parser.add_argument("--query-suffix", default="travel")
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
    parsed = parse.urlsplit(url)
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in {"utm_source", "utm_medium"}]
    pairs.append(("utm_source", UTM_SOURCE))
    pairs.append(("utm_medium", UTM_MEDIUM))
    query = parse.urlencode(pairs)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def infer_location_from_path(file_path: Path) -> Tuple[str, str]:
    rel = file_path.relative_to(PLACE_PHOTOS_DIR)
    parts = rel.parts
    if not parts:
        return ("Location", "travel")

    if parts == ("world.json",):
        return ("World", "travel")

    if parts[0] == "countries":
        country = slug_to_label(parts[1]) if len(parts) > 1 else ""
        if len(parts) == 3 and parts[2].startswith("_"):
            return (country, "travel")
        if len(parts) == 4 and parts[3].startswith("_"):
            subdivision = slug_to_label(parts[2])
            return (f"{subdivision}, {country}", "travel")
        if len(parts) >= 4 and not parts[-1].startswith("_"):
            city = slug_to_label(parts[-1].replace(".json", ""))
            if len(parts) >= 4:
                subdivision = slug_to_label(parts[-2])
                return (f"{city}, {subdivision}, {country}", "skyline city")
            return (f"{city}, {country}", "skyline city")

    return (slug_to_label(file_path.stem), "travel")


def infer_query(place_id: str, file_path: Path, query_suffix: str) -> str:
    if place_id.startswith("region:"):
        region = slug_to_label(place_id.split(":", 1)[1])
        base = region
    elif place_id.startswith("country:"):
        country = slug_to_label(place_id.split(":", 1)[1])
        base = country
    elif place_id.startswith("subdivision:"):
        _, country_slug, subdivision_slug = place_id.split(":", 2)
        base = f"{slug_to_label(subdivision_slug)}, {slug_to_label(country_slug)}"
    elif place_id.startswith("city:"):
        parts = place_id.split(":")
        if len(parts) >= 4:
            _, country_slug, subdivision_slug, city_slug = parts[:4]
            base = f"{slug_to_label(city_slug)}, {slug_to_label(subdivision_slug)}, {slug_to_label(country_slug)}"
        else:
            base, _ = infer_location_from_path(file_path)
    else:
        base, _ = infer_location_from_path(file_path)

    path_base, path_suffix = infer_location_from_path(file_path)
    if base != path_base:
        base = path_base

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


def build_photo_entry(existing: Dict[str, Any], photo: Dict[str, Any], query: str) -> Dict[str, Any]:
    updated = dict(existing)
    updated.update(
        {
            "photo_id": photo.get("id", ""),
            "photo_url": photo.get("urls", {}).get("regular", ""),
            "photographer_name": photo.get("user", {}).get("name", ""),
            "photographer_url": append_referral(photo.get("user", {}).get("links", {}).get("html", "")),
            "unsplash_url": append_referral(photo.get("links", {}).get("html", "")),
            "download_location": photo.get("links", {}).get("download_location", ""),
            "blur_hash": photo.get("blur_hash", ""),
            "query": query,
            "updated_at": time.strftime("%Y-%m-%d %I:%M %p UTC", time.gmtime()),
            "provider": "unsplash",
        }
    )
    return updated


def should_process(entry: Dict[str, Any], args: argparse.Namespace) -> bool:
    place_id = entry.get("place_id", "")
    if args.place_id_contains and args.place_id_contains.lower() not in place_id.lower():
        return False
    if not args.overwrite and entry.get("photo_url"):
        return False
    return True


def iter_photo_files(root: Path) -> List[Path]:
    files = sorted((root / "place_photos").rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")
    return files


def update_version_file(root: Path, dry_run: bool) -> None:
    version_path = root / "version.json"
    if not version_path.exists():
        return

    payload = load_json(version_path)
    payload["updated_at"] = time.strftime("%Y-%m-%d %I:%M %p UTC", time.gmtime())
    if dry_run:
        print(f"would update {version_path}")
        return
    save_json(version_path, payload)


def main() -> int:
    args = parse_args()
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
                print(f"error for {place_id}: {exc}", file=sys.stderr)
                continue

            payload[index] = build_photo_entry(entry, photo, query)
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

    if changed_files and not args.dry_run:
        update_version_file(root, dry_run=False)

    print(f"processed_entries={processed} changed_files={changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
