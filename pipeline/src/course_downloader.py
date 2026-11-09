"""Automated OpenStreetMap / Overpass Downloader for Golf Courses.

Resolves golf course geographical boundaries using OpenStreetMap (Nominatim/Overpass),
downloads raw elements, converts them to standard GeoJSON via osm2geojson,
and integrates directly with the GolfCourse domain model.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple
import requests
import osm2geojson

try:
    from .course_geometry import GolfCourse
except ImportError:
    from course_geometry import GolfCourse

# Configure paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
COURSES_OUTPUT_DIR = DATA_DIR / "courses"
REGISTRY_PATH = DATA_DIR / "courses_registry.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

_contact = os.environ.get("OSM_CONTACT_EMAIL", "https://github.com/golf-course-viewer")
USER_AGENT = f"HoleFeatureExtractor/1.0 (+{_contact}; golf research & geometry engine)"


def slugify(text: str) -> str:
    """Generate filesystem-safe slug from course name."""
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def clean_course_name_variants(course_name: str) -> list[str]:
    """Generate search variants for a course name to maximize OSM geocoding hit rate.

    Example:
      'Torrey Pines Golf Course (South Course)' ->
        ['Torrey Pines Golf Course (South Course)', 'Torrey Pines South Course', 'Torrey Pines Golf Course']
    """
    variants = [course_name.strip()]

    # Check for parenthetical course sub-name e.g. "TPC Sawgrass (THE PLAYERS Stadium Course)"
    match = re.search(r"^(.*?)\s*\((.*?)\)$", course_name)
    if match:
        main_facility = match.group(1).strip()
        sub_name = match.group(2).strip()

        # Variant: "TPC Sawgrass THE PLAYERS Stadium Course"
        variants.append(f"{main_facility} {sub_name}")
        # Variant: "THE PLAYERS Stadium Course"
        variants.append(sub_name)
        # Variant: "TPC Sawgrass"
        variants.append(main_facility)

    # Strip resort/club prefixes/suffixes
    for suffix in [" Golf Links", " Golf Course", " Golf Club", " Country Club", " Resort"]:
        if course_name.endswith(suffix):
            base = course_name[:-len(suffix)].strip()
            if base and base not in variants:
                variants.append(base)

    # De-duplicate while preserving order
    seen: set[str] = set()
    cleaned: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            cleaned.append(v)
    return cleaned


def geocode_course(
    course_name: str,
    timeout: float = 12.0,
) -> Optional[dict[str, Any]]:
    """Query Nominatim for course bounding box and OSM metadata."""
    headers = {"User-Agent": USER_AGENT}
    variants = clean_course_name_variants(course_name)

    for query in variants:
        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 3,
                "addressdetails": 1,
            }
            logging.info("Geocoding query: '%s'...", query)
            resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                time.sleep(1.0)
                continue

            results = resp.json()
            if not results:
                time.sleep(1.0)
                continue

            # Prioritize results that are leisure=golf_course or tourism/sports
            best_match = None
            for item in results:
                cat = item.get("category", "")
                typ = item.get("type", "")
                display = item.get("display_name", "").lower()
                if typ == "golf_course" or "golf" in typ or "golf" in display or cat == "leisure":
                    best_match = item
                    break

            if not best_match:
                best_match = results[0]

            raw_bbox = best_match.get("boundingbox")
            if raw_bbox and len(raw_bbox) == 4:
                # Nominatim bbox: [min_lat, max_lat, min_lon, max_lon]
                s, n, w, e = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])
                lat = float(best_match.get("lat"))
                lon = float(best_match.get("lon"))

                # If the returned bbox is too small (e.g. a point/clubhouse node rather than full course polygon),
                # expand to typical golf course radius (~1.5 km / ~0.015 deg lat, ~0.018 deg lon)
                min_span = 0.010
                if (n - s) < min_span or (e - w) < min_span:
                    logging.info("Nominatim bbox is small (likely clubhouse pin: %.4f x %.4f deg). Expanding to course radius...",
                                 (n - s), (e - w))
                    s = min(s, lat - 0.014)
                    n = max(n, lat + 0.014)
                    w = min(w, lon - 0.018)
                    e = max(e, lon + 0.018)

                return {
                    "matched_query": query,
                    "display_name": best_match.get("display_name"),
                    "osm_type": best_match.get("osm_type"),
                    "osm_id": best_match.get("osm_id"),
                    "lat": lat,
                    "lon": lon,
                    "bbox": (s, w, n, e),  # (south, west, north, east)
                }


        except Exception as e:
            logging.warning("Geocoding failed for '%s': %s", query, e)

        time.sleep(1.0)

    return None


def query_overpass_bbox(
    bbox: Tuple[float, float, float, float],
    pad_degrees: float = 0.002,
    timeout_sec: int = 90,
) -> dict[str, Any]:
    """Download all golf course features inside bounding box (south, west, north, east)."""
    s, w, n, e = bbox
    # Add buffer around course to catch surrounding hazards / tee markers
    s -= pad_degrees
    n += pad_degrees
    w -= pad_degrees
    e += pad_degrees

    # Note: avoid bare 'natural=water' as it pulls the entire ocean on coastal courses (like Pebble Beach)
    overpass_query = f"""
    [out:json][timeout:{timeout_sec}];
    (
      nwr["golf"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});
      nwr["leisure"="golf_course"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});
      nwr["water"~"pond|lake|reservoir|stream"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});
      nwr["natural"="water"]["water"!="ocean"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});
    );
    out body;
    >;
    out skel qt;
    """


    headers = {"User-Agent": USER_AGENT}
    last_error: Optional[Exception] = None

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            logging.info("Querying Overpass (%s) for bbox [%.4f, %.4f, %.4f, %.4f]...",
                         endpoint.split("/")[2], s, w, n, e)
            resp = requests.post(
                endpoint,
                data={"data": overpass_query},
                headers=headers,
                timeout=timeout_sec + 15,
            )
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                logging.info("Overpass returned %d raw OSM elements.", len(elements))
                if elements:
                    return data
            else:
                logging.warning("Overpass endpoint returned HTTP %s", resp.status_code)
        except Exception as err:
            logging.warning("Failed request to %s: %s", endpoint, err)
            last_error = err
        time.sleep(2.0)

    raise RuntimeError(f"Overpass query failed across all endpoints. Last error: {last_error}")


def download_course_geojson(
    course_name: str,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    output_path: Optional[Path] = None,
    force_refresh: bool = False,
) -> Path:
    """Resolve, download, convert and cache GeoJSON for a golf course."""
    COURSES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(course_name)

    if output_path is None:
        target_path = COURSES_OUTPUT_DIR / f"{slug}.geojson"
    else:
        target_path = Path(output_path)

    if target_path.exists() and not force_refresh:
        logging.info("Found cached GeoJSON at: %s", target_path)
        return target_path

    # Step 1: Resolve Bounding Box if not supplied
    if not bbox:
        geo_info = geocode_course(course_name)
        if not geo_info or not geo_info.get("bbox"):
            raise ValueError(f"Could not resolve geographical location for course: '{course_name}'")
        bbox = geo_info["bbox"]
        logging.info("Resolved '%s' -> %s (bbox: %s)", course_name, geo_info["display_name"], bbox)

    # Step 2: Download raw OSM elements via Overpass
    raw_osm = query_overpass_bbox(bbox)

    # Step 3: Convert to standard GeoJSON
    logging.info("Converting OSM elements to GeoJSON with osm2geojson...")
    geojson_dict = osm2geojson.json2geojson(raw_osm)

    features = geojson_dict.get("features", [])
    logging.info("Generated %d GeoJSON features. Flattening OSM tags...", len(features))

    # Overpass Turbo flattens tags directly into properties; osm2geojson puts them in properties['tags'].
    # Flatten tags into properties for full compatibility with GolfCourse.from_geojson.
    for feat in features:
        props = feat.setdefault("properties", {})
        tags = props.get("tags")
        if isinstance(tags, dict):
            for k, v in tags.items():
                if k not in props:
                    props[k] = v
        # Ensure @id exists
        if "@id" not in props and "id" in props:
            props["@id"] = f"{props.get('type', 'element')}/{props['id']}"


    # Add metadata to GeoJSON
    geojson_dict["properties"] = {
        "course_name": course_name,
        "slug": slug,
        "bbox": list(bbox),
        "source": "OpenStreetMap via Overpass API",
        "download_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Step 4: Write to disk
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, indent=2)

    logging.info("Saved course GeoJSON: %s (%.1f KB)", target_path, target_path.stat().st_size / 1024)
    return target_path


def get_or_download_course(
    course_identifier: str,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    force_refresh: bool = False,
) -> GolfCourse:
    """High-level function: download if needed and return an initialized GolfCourse object."""
    # Check if identifier matches a registered course in courses_registry.json
    course_name = course_identifier
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, encoding="utf-8") as f:
                reg = json.load(f)
            # Check by course ID
            if course_identifier in reg.get("courses_by_id", {}):
                course_name = reg["courses_by_id"][course_identifier]["course_name"]
            # Check by course name
            elif course_identifier in reg.get("courses", {}):
                course_name = reg["courses"][course_identifier]["course_name"]
            # Check by tournament ID
            elif course_identifier in reg.get("tournaments", {}):
                t_courses = reg["tournaments"][course_identifier].get("courses", [])
                if t_courses:
                    # Pick host course if available, or first
                    host_c = next((c for c in t_courses if c.get("host_course")), t_courses[0])
                    course_name = host_c["course_name"]
        except Exception as e:
            logging.warning("Error reading courses_registry.json: %s", e)

    geojson_path = download_course_geojson(
        course_name=course_name,
        bbox=bbox,
        force_refresh=force_refresh,
    )

    logging.info("Ingesting GeoJSON into GolfCourse domain model...")
    try:
        course = GolfCourse.from_geojson(geojson_path, target_course_name=course_name)
    except Exception as e:
        logging.warning("Failed with target_course_name filter (%s). Loading without course name filter...", e)
        course = GolfCourse.from_geojson(geojson_path)
    return course



def main():
    parser = argparse.ArgumentParser(description="Download Golf Course GeoJSON from OpenStreetMap / Overpass")
    parser.add_argument("course", help="Course name, PGA course ID (e.g. 011), or Tournament ID (e.g. R2025005)")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("SOUTH", "WEST", "NORTH", "EAST"),
                        help="Explicit bounding box coordinates (south west north east)")
    parser.add_argument("--output", "-o", default=None, help="Output GeoJSON file path")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cached")
    parser.add_argument("--export-html", default=None, help="Export interactive HTML viewer after download")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    bbox_tuple = tuple(args.bbox) if args.bbox else None
    course = get_or_download_course(
        course_identifier=args.course,
        bbox=bbox_tuple,
        force_refresh=args.force,
    )

    print("\n" + "=" * 60)
    print(f"COURSE LOADED: {course.name}")
    print(f"Total Holes Detected: {len(course.holes)}")
    print("=" * 60)

    for h_num in sorted(course.holes.keys()):
        hole = course.holes[h_num]
        green_status = "Yes" if hole.green else "No"
        print(f"  Hole {hole.hole_number:2d}: Par {hole.par}, Length {hole.length_yards} yds | "
              f"Green: {green_status}, Tees: {len(hole.tee_boxes)}, Fairways: {len(hole.fairways)}, "
              f"Bunkers: {len(hole.bunkers)}, Water: {len(hole.water_hazards)}")


    if args.export_html:
        try:
            from .interactive_viewer import export_interactive_html
        except ImportError:
            from interactive_viewer import export_interactive_html
        export_interactive_html(course, args.export_html)

        print(f"\nInteractive viewer exported to: {args.export_html}")


if __name__ == "__main__":
    main()
