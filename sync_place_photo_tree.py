#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


MAX_STALE_DELETE_RATIO = 0.10
REQUIRED_PHOTO_FIELDS = [
    "place_id",
    "image_url",
    "photographer_name",
    "photographer_url",
    "source_url",
]
PHOTO_FIELDS = [
    "image_url",
    "photographer_name",
    "photographer_url",
    "source_url",
    "cached_at",
]


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


def has_cached_photo(entry):
    if not isinstance(entry, dict):
        return False

    for field in REQUIRED_PHOTO_FIELDS:
        value = entry.get(field, "")
        if not isinstance(value, str) or not value.strip():
            return False

    return True


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

    if not isinstance(target_data, list):
        return False

    if not target_data:
        write_json_file(target_file, get_blank_photo_data(expected_place_id))
        return True

    first_entry = target_data[0]

    if not isinstance(first_entry, dict):
        return False

    normalized_first_entry = {
        "place_id": expected_place_id,
        "image_url": first_entry.get("image_url", ""),
        "photographer_name": first_entry.get("photographer_name", ""),
        "photographer_url": first_entry.get("photographer_url", ""),
        "source_url": first_entry.get("source_url", ""),
        "cached_at": first_entry.get("cached_at", ""),
    }

    if len(target_data) == 1 and first_entry == normalized_first_entry:
        return False

    target_data[0] = normalized_first_entry
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


def build_current_file_index(photo_root, expected_files):
    current_file_index = {}

    for target_file in expected_files:
        relative_path = target_file.relative_to(photo_root)
        parts = relative_path.parts

        if len(parts) < 3:
            continue

        file_name = target_file.name
        if file_name.startswith("_"):
            continue

        country_slug = parts[0]
        key = (country_slug, file_name)
        current_file_index.setdefault(key, []).append(target_file)

    return current_file_index


def migrate_stale_photo(stale_file, canonical_file):
    stale_data = load_json_file(stale_file)
    canonical_data = load_json_file(canonical_file)

    if not isinstance(stale_data, list) or not stale_data:
        return False

    if not isinstance(canonical_data, list) or not canonical_data:
        return False

    stale_entry = stale_data[0]
    canonical_entry = canonical_data[0]

    if not has_cached_photo(stale_entry):
        return False

    if has_cached_photo(canonical_entry):
        return False

    if not isinstance(canonical_entry, dict):
        return False

    migrated_entry = dict(canonical_entry)

    for field in PHOTO_FIELDS:
        if field == "cached_at" and not str(stale_entry.get(field, "")).strip():
            continue

        migrated_entry[field] = stale_entry.get(field, "")

    canonical_data[0] = migrated_entry
    write_json_file(canonical_file, canonical_data)

    return True


def prune_empty_directories(photo_root):
    removed_directories = 0

    for directory in sorted(photo_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not directory.is_dir():
            continue

        try:
            directory.rmdir()
            removed_directories += 1
        except OSError:
            continue

    return removed_directories


def validate_prune_scope(photo_root, expected_files, stale_files):
    current_files = sorted(photo_root.rglob("*.json"))

    if not expected_files:
        raise RuntimeError("refusing to prune stale photos because the source tree produced no expected files")

    if not current_files:
        raise RuntimeError("refusing to prune stale photos because the public photo tree has no json files")

    max_deletions = int(len(current_files) * MAX_STALE_DELETE_RATIO)
    if max_deletions < 1:
        max_deletions = 1

    if len(stale_files) > max_deletions:
        raise RuntimeError(
            "refusing to prune stale photos because "
            f"{len(stale_files)} of {len(current_files)} files would be deleted, "
            f"which exceeds the {MAX_STALE_DELETE_RATIO:.0%} safety limit"
        )


def prune_stale_photo_files(photo_root, expected_files):
    expected_paths = set()
    migrated_files = 0
    deleted_files = 0
    current_file_index = build_current_file_index(photo_root, expected_files)

    for expected_file in expected_files:
        expected_paths.add(expected_file.resolve())

    stale_files = [
        file_path
        for file_path in sorted(photo_root.rglob("*.json"))
        if file_path.resolve() not in expected_paths
    ]

    validate_prune_scope(photo_root, expected_files, stale_files)

    for stale_file in stale_files:
        relative_path = stale_file.relative_to(photo_root)
        parts = relative_path.parts
        key = (parts[0], stale_file.name) if len(parts) >= 3 else None
        canonical_files = current_file_index.get(key, []) if key else []

        if len(canonical_files) == 1:
            if migrate_stale_photo(stale_file, canonical_files[0]):
                migrated_files += 1
                print(f"migrated cached photo from {relative_path} to {canonical_files[0].relative_to(photo_root)}")

        stale_file.unlink()
        deleted_files += 1
        print(f"deleted stale photo file {relative_path}")

    removed_directories = prune_empty_directories(photo_root)

    return (migrated_files, deleted_files, removed_directories)


def sync_place_photo_tree(source_root, photo_root, prune_stale):
    created_or_updated_files = 0
    expected_files = []

    for source_file in sorted(source_root.rglob("*.json")):
        relative_path = source_file.relative_to(source_root)
        target_file = photo_root.joinpath(*relative_path.parts)
        expected_files.append(target_file)
        created_or_updated_files += sync_file(source_file, target_file)

    migrated_files = 0
    deleted_files = 0
    removed_directories = 0

    if prune_stale:
        migrated_files, deleted_files, removed_directories = prune_stale_photo_files(photo_root, expected_files)

    return (created_or_updated_files, migrated_files, deleted_files, removed_directories)


def main():
    parser = argparse.ArgumentParser(description="sync public place photo placeholders from app place data")
    parser.add_argument("--source-root", required=True, help="source countries directory from the app repo")
    parser.add_argument("--photo-root", required=True, help="public-assets place photo countries directory")
    parser.add_argument("--prune-stale", action="store_true", help="delete photo files no longer present in the source tree")

    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    photo_root = Path(args.photo_root).resolve()

    if not source_root.exists():
        raise FileNotFoundError(f"source root does not exist: {source_root}")

    if not source_root.is_dir():
        raise NotADirectoryError(f"source root is not a directory: {source_root}")

    created_or_updated_files, migrated_files, deleted_files, removed_directories = sync_place_photo_tree(
        source_root,
        photo_root,
        args.prune_stale,
    )

    print(f"created or updated {created_or_updated_files} place photo files")
    print(f"migrated {migrated_files} cached photos from stale files")
    print(f"deleted {deleted_files} stale photo files")
    print(f"removed {removed_directories} empty photo directories")


if __name__ == "__main__":
    main()
