#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_json_file(file_path):
    try:
        with file_path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except json.JSONDecodeError:
        return None


def get_label(data, fallback):
    label = data.get("label")

    if isinstance(label, str) and label.strip():
        return label.strip()

    return fallback.replace("-", " ").replace("_", " ").title()


def get_place_id(data):
    place_id = data.get("place_id")

    if isinstance(place_id, str) and place_id.strip():
        return place_id.strip()

    return ""


def get_blank_photo_data(place_id, label):
    return {
        "place_id": place_id,
        "label": label,
        "photo": {}
    }


def write_json_file(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)
        file_handle.write("\n")


def sync_self_file(source_file, target_file):
    source_data = load_json_file(source_file)

    if not isinstance(source_data, dict):
        return False

    place_id = get_place_id(source_data)
    label = get_label(source_data, source_file.parent.name)

    if not place_id:
        return False

    if target_file.exists():
        return False

    write_json_file(target_file, get_blank_photo_data(place_id, label))

    return True


def sync_city_file(source_file, target_file):
    source_data = load_json_file(source_file)

    if not isinstance(source_data, dict):
        return False

    place_id = get_place_id(source_data)
    label = get_label(source_data, source_file.stem)

    if not place_id:
        return False

    if target_file.exists():
        return False

    write_json_file(target_file, get_blank_photo_data(place_id, label))

    return True


def sync_place_photo_tree(source_root, photo_root):
    created_files = 0

    for source_file in sorted(source_root.rglob("*.json")):
        relative_path = source_file.relative_to(source_root)
        path_parts = relative_path.parts

        if source_file.name.startswith("_"):
            target_file = photo_root.joinpath(*relative_path.parent.parts, "_self.json")
            if sync_self_file(source_file, target_file):
                created_files += 1
            continue

        target_file = photo_root.joinpath(*relative_path.parts)

        if sync_city_file(source_file, target_file):
            created_files += 1

    return created_files


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

    created_files = sync_place_photo_tree(source_root, photo_root)

    print(f"created {created_files} missing place photo placeholder files")


if __name__ == "__main__":
    main()
