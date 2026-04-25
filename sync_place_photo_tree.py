#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_json_file(file_path):
    try:
        with file_path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return None


def get_first_entry(data):
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]

    if isinstance(data, dict):
        return data

    return None


def get_place_id(entry):
    if not isinstance(entry, dict):
        return ""

    place_id = entry.get("place_id") or entry.get("id")

    if isinstance(place_id, str) and place_id.strip():
        return place_id.strip()

    return ""


def get_label(entry, fallback):
    if isinstance(entry, dict):
        label = entry.get("label")

        if isinstance(label, str) and label.strip():
            return label.strip()

    return fallback.replace("-", " ").replace("_", " ").title()


def get_blank_photo_data(place_id):
    return [
        {
            "place_id": place_id,
            "image_url": "",
            "photographer_name": "",
            "photographer_url": "",
            "source_url": "",
            "cached_at": ""
        }
    ]


def write_json_file(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)
        file_handle.write("\n")


def normalize_existing_photo_file(target_file, expected_place_id):
    target_data = load_json_file(target_file)

    if not isinstance(target_data, list) or not target_data:
        return False

    first_entry = target_data[0]

    if not isinstance(first_entry, dict):
        return False

    current_place_id = first_entry.get("place_id", "")

    if current_place_id == expected_place_id:
        return False

    first_entry["place_id"] = expected_place_id
    write_json_file(target_file, target_data)

    return True


def sync_file(source_file, target_file):
    source_data = load_json_file(source_file)
    source_entry = get_first_entry(source_data)

    if not isinstance(source_entry, dict):
        return 0

    place_id = get_place_id(source_entry)

    if not place_id:
        return 0

    if target_file.exists():
        return 1 if normalize_existing_photo_file(target_file, place_id) else 0

    write_json_file(target_file, get_blank_photo_data(place_id))

    return 1


def sync_place_photo_tree(source_root, photo_root):
    created_or_updated_files = 0

    for source_file in sorted(source_root.rglob("*.json")):
        relative_path = source_file.relative_to(source_root)
        target_file = photo_root.joinpath(*relative_path.parts)
        created_or_updated_files += sync_file(source_file, target_file)

    return created_or_updated_files


def main():
    parser = argparse.ArgumentParser(description="sync public place photo placeholders from app place data")
    parser.add_argument("--source-root", required=True, help="source countries directory from the app repo")
    parser.add_argument("--photo-root", required=True, help="public-assets place photo countries directory")

    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    photo_root = Path(args.photo_root).resolve()

    if not source_root.exists():
        raise FileNotFoundError(f"source root does not exist: {source_root}")

    if not source_root.is_dir():
        raise NotADirectoryError(f"source root is not a directory: {source_root}")

    created_or_updated_files = sync_place_photo_tree(source_root, photo_root)

    print(f"created or updated {created_or_updated_files} place photo files")


if __name__ == "__main__":
    main()
