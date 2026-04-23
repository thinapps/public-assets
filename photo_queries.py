import re
from pathlib import Path
from typing import Dict, List, Optional


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


def infer_place_id_from_path(place_photos_dir: Path, file_path: Path) -> Optional[str]:
    # infer a single place_id from normal country, subdivision, or city file paths
    rel = file_path.relative_to(place_photos_dir)
    parts = rel.parts

    if not parts or parts == ("world.json",):
        return None

    if parts[0] != "countries" or len(parts) < 3:
        return None

    country_slug = parts[1].replace("-", "_")

    if len(parts) == 3 and parts[2].startswith("_"):
        return f"country:{country_slug}"

    if len(parts) == 4 and parts[3].startswith("_"):
        subdivision_slug = parts[2].replace("-", "_")
        return f"subdivision:{country_slug}:{subdivision_slug}"

    if len(parts) >= 4 and not parts[-1].startswith("_"):
        subdivision_slug = parts[-2].replace("-", "_")
        city_slug = file_path.stem.replace("-", "_")
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
