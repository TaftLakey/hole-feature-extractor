#!/usr/bin/env python3
"""build_site_data.py - Build and validate static site data for the Golf Course Hole Viewer web app.

Usage:
    python pipeline/scripts/build_site_data.py "Quail Hollow Club"      # add or refresh one course
    python pipeline/scripts/build_site_data.py --all                     # rebuild all courses from cache
    python pipeline/scripts/build_site_data.py "TPC Sawgrass" --force    # force re-download from OSM
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

# Ensure pipeline root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PIPELINE_ROOT.parent

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from src.course_downloader import COURSES_OUTPUT_DIR, DATA_DIR, REGISTRY_PATH, get_or_download_course, slugify
from src.course_geometry import GolfCourse
from src.generate_course_viewers import find_course_geojson_files, load_registry_meta, match_course_registry
from src.interactive_viewer import serialize_course_data
from src.schema import CourseIndexEntry, CoursesIndex, DataAttribution, validate_course_data, validate_courses_index

# Default output locations
WEB_PUBLIC_DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"
COURSES_JSON_DIR = WEB_PUBLIC_DATA_DIR / "courses"
INDEX_JSON_PATH = WEB_PUBLIC_DATA_DIR / "courses.json"


def atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON data to file using a temporary file and rename."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=str(file_path.parent), prefix=".tmp_build_", suffix=".json")
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Atomic rename
        os.replace(temp_path, str(file_path))
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def audit_course_quality(serialized: dict[str, Any]) -> list[str]:
    """Inspect serialized course data for data-quality problems and return warnings."""
    warnings: list[str] = []
    course_name = serialized.get("course_name", "Unknown Course")
    holes = serialized.get("holes", [])

    if len(holes) < 18:
        warnings.append(f"Course has only {len(holes)} holes (expected 18).")

    for h in holes:
        h_num = h.get("number")
        paths = h.get("paths", {})
        h_up = paths.get("hole_up", {})
        pin = h.get("pin", {}).get("hole_up", {})
        tee = h.get("tee", {}).get("hole_up", {})

        if not h_up.get("green"):
            warnings.append(f"Hole {h_num}: Missing green geometry.")
        if not h_up.get("tees") and not h_up.get("fairways"):
            warnings.append(f"Hole {h_num}: Missing tee geometry.")
        if pin.get("x") is None or pin.get("y") is None:
            warnings.append(f"Hole {h_num}: Missing pin coordinates.")
        if tee.get("x") is None or tee.get("y") is None:
            warnings.append(f"Hole {h_num}: Missing tee coordinates.")
        if not h_up.get("centerline"):
            warnings.append(f"Hole {h_num}: Missing centerline geometry.")

    return warnings


def resolve_course_metadata(slug: str, course_name: str, registry: dict[str, Any]) -> dict[str, Any]:
    """Extract public course metadata, excluding internal PGA IDs or scoring levels."""
    raw_meta = match_course_registry(slug, course_name, registry)
    tournaments = []
    for t in raw_meta.get("tournaments", []):
        t_name = t.get("tournament_name")
        if t_name and t_name not in tournaments:
            tournaments.append(t_name)

    return {
        "course_name": raw_meta.get("course_name") or course_name,
        "tournaments": tournaments,
    }


def build_single_course(
    course_input: str | Path,
    output_dir: Path,
    registry: dict[str, Any],
    force: bool = False,
) -> tuple[dict[str, Any], Path, list[str]]:
    """Build, validate and write a single course JSON. Returns (index_entry, json_path, warnings)."""
    output_courses_dir = output_dir / "courses"
    output_courses_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(course_input, Path):
        logging.info("Loading course from GeoJSON path: %s", course_input)
        course = GolfCourse.from_geojson(course_input)
        slug = course_input.stem.lower()
        if slug == "augusta":
            slug = "augusta_national_golf_club"
    else:
        logging.info("Resolving course identifier '%s'...", course_input)
        course = get_or_download_course(course_input, force_refresh=force)
        slug = slugify(course.name)

    # Serialize course
    logging.info("Serializing geometry for '%s' (slug: %s)...", course.name, slug)
    serialized = serialize_course_data(course)

    # Align metadata
    meta = resolve_course_metadata(slug, serialized["course_name"], registry)
    serialized["course_name"] = meta["course_name"]

    # Audit quality
    warnings = audit_course_quality(serialized)

    # Validate against Pydantic schema
    validate_course_data(serialized)

    # Write atomically
    target_path = output_courses_dir / f"{slug}.json"
    atomic_write_json(target_path, serialized)
    logging.info("Wrote validated course JSON to %s (%d bytes)", target_path, target_path.stat().st_size)

    entry = {
        "slug": slug,
        "name": serialized["course_name"],
        "holes": serialized["total_holes"],
        "par": serialized["total_par"],
        "yards": serialized["total_yards"],
        "tournaments": meta["tournaments"],
        "data_file": f"courses/{slug}.json",
    }
    return entry, target_path, warnings


def regenerate_courses_index(output_dir: Path, registry: dict[str, Any]) -> Path:
    """Scan all course JSON files in output_dir/courses and rebuild courses.json index."""
    courses_dir = output_dir / "courses"
    index_file = output_dir / "courses.json"

    entries: list[dict[str, Any]] = []
    if courses_dir.exists():
        for json_path in sorted(courses_dir.glob("*.json")):
            if json_path.name.startswith("."):
                continue
            with open(json_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)

            slug = json_path.stem
            meta = resolve_course_metadata(slug, c_data.get("course_name", slug), registry)
            entries.append({
                "slug": slug,
                "name": meta["course_name"],
                "holes": c_data.get("total_holes", 0),
                "par": c_data.get("total_par", 0),
                "yards": c_data.get("total_yards", 0),
                "tournaments": meta["tournaments"],
                "data_file": f"courses/{json_path.name}",
            })

    index_payload = {
        "schema_version": "1.0.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data_attribution": {
            "name": "OpenStreetMap contributors",
            "url": "https://www.openstreetmap.org/copyright",
            "license": "ODbL 1.0",
        },
        "courses": entries,
    }

    # Validate index against schema
    validate_courses_index(index_payload)

    atomic_write_json(index_file, index_payload)
    logging.info("Updated courses index at %s with %d courses.", index_file, len(entries))
    return index_file


def main():
    parser = argparse.ArgumentParser(description="Build and validate static site data for Golf Course Viewer.")
    parser.add_argument("course", nargs="?", default=None, help="Course name, PGA course ID, or Tournament ID")
    parser.add_argument("--all", action="store_true", help="Rebuild all cached course GeoJSON files in data/")
    parser.add_argument("--force", action="store_true", help="Force re-download from OpenStreetMap even if cached")
    parser.add_argument("--output-dir", default=str(WEB_PUBLIC_DATA_DIR), help="Output directory for site data")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    out_dir = Path(args.output_dir).resolve()
    registry = load_registry_meta()

    if not args.all and not args.course:
        parser.print_help()
        sys.exit(1)

    built_summaries = []
    all_warnings = []

    try:
        if args.all:
            # Discover all cached GeoJSON files
            discovered = find_course_geojson_files()
            if not discovered:
                logging.error("No course GeoJSON files found in data/ or data/courses/")
                sys.exit(1)

            # Deduplicate by slug
            seen_slugs = set()
            unique_discovered = []
            for slug, path in discovered:
                resolved_slug = "augusta_national_golf_club" if slug == "augusta" else slug
                if resolved_slug not in seen_slugs:
                    seen_slugs.add(resolved_slug)
                    unique_discovered.append((resolved_slug, path))

            print(f"\nBuilding all {len(unique_discovered)} discovered courses into: {out_dir}\n" + "=" * 60)
            for slug, geojson_path in unique_discovered:
                entry, json_path, warnings = build_single_course(
                    course_input=geojson_path,
                    output_dir=out_dir,
                    registry=registry,
                    force=args.force,
                )
                built_summaries.append((entry, json_path))
                if warnings:
                    all_warnings.append((entry["name"], warnings))

        else:
            print(f"\nBuilding course '{args.course}' into: {out_dir}\n" + "=" * 60)
            entry, json_path, warnings = build_single_course(
                course_input=args.course,
                output_dir=out_dir,
                registry=registry,
                force=args.force,
            )
            built_summaries.append((entry, json_path))
            if warnings:
                all_warnings.append((entry["name"], warnings))

        # Rebuild index
        regenerate_courses_index(output_dir=out_dir, registry=registry)

        # Print summary
        print("\n" + "=" * 60)
        print("BUILD SUMMARY:")
        print(f"{'Course Name':<35} {'Holes':<6} {'Par':<5} {'Yards':<7} {'Size':<10}")
        print("-" * 65)
        for entry, path in built_summaries:
            sz_kb = f"{path.stat().st_size / 1024:.1f} KB"
            print(f"{entry['name']:<35} {entry['holes']:<6} {entry['par']:<5} {entry['yards']:<7} {sz_kb:<10}")
        print("=" * 60)

        if all_warnings:
            print("\n[!] DATA QUALITY WARNINGS:")
            for c_name, w_list in all_warnings:
                print(f"\n[{c_name}]")
                for w in w_list:
                    print(f"  - {w}")
            print("\nCheck the above warnings to ensure courses render accurately.")

        print("\n[OK] Build completed successfully!\n")

    except Exception as e:
        logging.error("Build failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
