#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FIELDS = (
    "place_id",
    "image_url",
    "photographer_name",
    "photographer_url",
    "source_url",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def usable_photo(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    return all(clean_string(entry.get(field, "")) for field in REQUIRED_FIELDS)


def build_lookup(place_photos_dir: Path) -> Dict[str, Dict[str, str]]:
    files = sorted(place_photos_dir.rglob("*.json"))
    if not files:
        raise RuntimeError("no place_photos json files found")

    photos: Dict[str, Dict[str, str]] = {}
    for file_path in files:
        payload = load_json(file_path)
        if not isinstance(payload, list):
            continue

        for entry in payload:
            if not usable_photo(entry):
                continue

            place_id = clean_string(entry["place_id"])
            photo = {
                "image_url": clean_string(entry["image_url"]),
                "photographer_name": clean_string(entry["photographer_name"]),
                "photographer_url": clean_string(entry["photographer_url"]),
                "source_url": clean_string(entry["source_url"]),
            }

            existing = photos.get(place_id)
            if existing is not None and existing != photo:
                raise RuntimeError(f"conflicting photo metadata for {place_id}")
            photos[place_id] = photo

    return dict(sorted(photos.items()))


def write_lookup(path: Path, photos: Dict[str, Dict[str, str]]) -> bool:
    payload = json.dumps(photos, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        print(f"no photo lookup changes for {path}")
        return False

    path.write_text(payload, encoding="utf-8", newline="\n")
    print(f"updated {path} with {len(photos)} photos")
    return True


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    place_photos_dir = root / "place_photos"
    output_path = root / "photos.json"

    photos = build_lookup(place_photos_dir)
    write_lookup(output_path, photos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
