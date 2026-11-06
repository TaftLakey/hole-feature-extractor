"""Batch generator for interactive HTML golf course viewers and portal dashboard.

Scans data/ and data/courses/ for downloaded GeoJSON course files,
enriches them with metadata from courses_registry.json, exports standalone
interactive vector HTML viewers into output/viewers/, and generates a
modern index.html hub to launch and inspect any course.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from .course_geometry import GolfCourse
from .interactive_viewer import export_interactive_html

# Directory paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
COURSES_DATA_DIR = DATA_DIR / "courses"
REGISTRY_PATH = DATA_DIR / "courses_registry.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
VIEWERS_OUTPUT_DIR = OUTPUT_DIR / "viewers"


def find_course_geojson_files() -> list[tuple[str, Path]]:
    """Discover all available golf course GeoJSON files."""
    files: list[tuple[str, Path]] = []

    # Check root data/
    for p in DATA_DIR.glob("*.geojson"):
        slug = p.stem.lower()
        files.append((slug, p))

    # Check data/courses/
    if COURSES_DATA_DIR.exists():
        for p in COURSES_DATA_DIR.glob("*.geojson"):
            slug = p.stem.lower()
            if not any(f[0] == slug for f in files):
                files.append((slug, p))

    return files


def load_registry_meta() -> dict[str, Any]:
    """Load tournament and course metadata from courses_registry.json."""
    if not REGISTRY_PATH.exists():
        return {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning("Failed to load courses_registry.json: %s", e)
        return {}


def _clean_tokens(s: str) -> set[str]:
    """Extract distinguishing course words by removing generic stop words."""
    stopwords = {"golf", "course", "club", "links", "resort", "the", "at", "country", "national"}
    cleaned_str = s.lower().replace("_", " ").replace("-", " ")
    tokens = {w for w in re.findall(r"[a-z]{3,}", cleaned_str) if w not in stopwords}
    return tokens



def match_course_registry(slug: str, course_name: str, registry: dict[str, Any]) -> dict[str, Any]:
    """Find matching metadata for a course in the registry using salient keyword matching."""
    courses_map = registry.get("courses", {})

    # 1. Exact match
    if course_name in courses_map:
        return courses_map[course_name]

    # Special well-known course mappings
    if "augusta" in slug.lower() or "augusta" in course_name.lower():
        return {
            "course_name": "Augusta National Golf Club",
            "course_id": "014",
            "course_code": "AN",
            "scoring_level": "TOURCAST",
            "tournaments": [{"tournament_id": "R2025014", "tournament_name": "Masters Tournament", "host_course": True}],
        }

    # 2. Token overlap search on distinctive keywords
    target_tokens = _clean_tokens(slug) | _clean_tokens(course_name)

    best_match = None
    best_score = 0

    for reg_name, meta in courses_map.items():
        reg_tokens = _clean_tokens(reg_name)
        overlap = len(target_tokens & reg_tokens)
        if overlap > best_score:
            best_score = overlap
            best_match = meta

    if best_match and best_score >= 1:
        return best_match

    return {
        "course_name": course_name,
        "course_id": "",
        "course_code": "",
        "scoring_level": "CUSTOM",
        "tournaments": [],
    }



def build_dashboard_html(courses_summary: list[dict[str, Any]]) -> str:
    """Generate modern, responsive HTML dashboard linking all course viewers."""
    cards_html = []

    for c in courses_summary:
        tournaments_str = ""
        if c.get("tournaments"):
            t_names = [t.get("tournament_name") for t in c["tournaments"] if t.get("tournament_name")]
            if t_names:
                tournaments_str = f"""<div class="tournament-tag">{t_names[0]}</div>"""

        badge = f"""<span class="badge">{c.get('hole_count', 0)} Holes</span>"""
        par_str = f"Par {c.get('total_par', 72)}" if c.get("total_par") else ""
        yds_str = f"{c.get('total_yards', 0):,} yds" if c.get("total_yards") else ""

        cards_html.append(f"""
        <div class="course-card">
            <div class="card-header">
                {tournaments_str}
                <div class="badge-group">
                    {badge}
                    <span class="badge secondary">{c.get('course_id') or 'OSM'}</span>
                </div>
            </div>
            <h2 class="course-name">{c['name']}</h2>
            <div class="course-stats">
                <div class="stat-pill"><strong>{par_str}</strong></div>
                <div class="stat-pill"><strong>{yds_str}</strong></div>
                <div class="stat-pill">{c.get('bunkers_count', 0)} Bunkers</div>
                <div class="stat-pill">{c.get('water_count', 0)} Hazards</div>
            </div>
            <div class="card-footer">
                <a href="viewers/{c['viewer_filename']}" target="_blank" class="launch-btn">
                    Launch Interactive Viewer &rarr;
                </a>
            </div>
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PGA Tour Courses &mdash; Interactive Vector Viewers</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-page: #0b0f17;
            --bg-card: #131b26;
            --bg-card-hover: #1a2433;
            --border: #223044;
            --accent-green: #2ecc71;
            --accent-green-hover: #27ae60;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background-color: var(--bg-page);
            color: var(--text-main);
            font-family: var(--font-family);
            line-height: 1.5;
            padding: 40px 24px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 40px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 24px;
        }}
        .header-title-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }}
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .flag-icon {{
            font-size: 1.8rem;
        }}
        .subtitle {{
            color: var(--text-muted);
            margin-top: 6px;
            font-size: 1rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 24px;
        }}
        .course-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        .course-card:hover {{
            transform: translateY(-2px);
            border-color: #334863;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
        }}
        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
        }}
        .tournament-tag {{
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--accent-green);
            background: rgba(46, 204, 113, 0.12);
            padding: 4px 10px;
            border-radius: 6px;
        }}
        .badge-group {{
            display: flex;
            gap: 6px;
        }}
        .badge {{
            font-size: 0.75rem;
            font-weight: 600;
            background: #1e293b;
            color: #cbd5e1;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid #334155;
        }}
        .badge.secondary {{
            color: #94a3b8;
        }}
        .course-name {{
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 16px;
            line-height: 1.3;
        }}
        .course-stats {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 24px;
        }}
        .stat-pill {{
            background: #0f172a;
            border: 1px solid #1e293b;
            padding: 5px 10px;
            border-radius: 8px;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        .stat-pill strong {{
            color: var(--text-main);
        }}
        .card-footer {{
            margin-top: auto;
        }}
        .launch-btn {{
            display: block;
            width: 100%;
            text-align: center;
            background: var(--accent-green);
            color: #05160d;
            font-weight: 600;
            font-size: 0.95rem;
            padding: 12px 18px;
            border-radius: 10px;
            text-decoration: none;
            transition: background 0.15s ease, transform 0.1s ease;
        }}
        .launch-btn:hover {{
            background: var(--accent-green-hover);
            transform: scale(1.01);
        }}
        footer {{
            margin-top: 60px;
            text-align: center;
            color: #475569;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title-row">
                <div>
                    <h1><span class="flag-icon">⛳</span> PGA Tour Interactive Course Viewers</h1>
                    <p class="subtitle">Geographical vector engines, hole-by-hole routing, and shot-planning models</p>
                </div>
                <div class="badge">{len(courses_summary)} Courses Loaded</div>
            </div>
        </header>

        <main class="grid">
            {''.join(cards_html)}
        </main>

        <footer>
            Hole Feature Extractor &bull; OpenStreetMap &amp; PGA Tour Analytics Platform
        </footer>
    </div>
</body>
</html>
"""


def process_all_courses(force_regenerate: bool = False) -> None:
    """Ingest GeoJSON courses, generate HTML viewers, and build index dashboard."""
    VIEWERS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = load_registry_meta()
    geojson_files = find_course_geojson_files()

    logging.info("Found %d GeoJSON course files to process.", len(geojson_files))
    courses_summary: list[dict[str, Any]] = []

    for slug, path in geojson_files:
        logging.info("--- Processing: %s (%s) ---", slug, path.name)
        viewer_filename = f"{slug}_viewer.html"
        viewer_path = VIEWERS_OUTPUT_DIR / viewer_filename

        try:
            course = GolfCourse.from_geojson(path)
            reg_meta = match_course_registry(slug, course.name, registry)

            total_par = sum(h.par for h in course.holes.values())
            total_yards = sum(h.length_yards for h in course.holes.values())
            total_bunkers = sum(len(h.bunkers) for h in course.holes.values())
            total_waters = sum(len(h.water_hazards) for h in course.holes.values())

            # Export HTML viewer
            if force_regenerate or not viewer_path.exists():
                logging.info("Exporting viewer to %s...", viewer_path)
                export_interactive_html(course, viewer_path)
            else:
                logging.info("Viewer already exists at %s. Skipping generation.", viewer_path)

            courses_summary.append({
                "slug": slug,
                "name": reg_meta.get("course_name") or course.name,
                "course_id": reg_meta.get("course_id", ""),
                "tournaments": reg_meta.get("tournaments", []),
                "hole_count": len(course.holes),
                "total_par": total_par,
                "total_yards": total_yards,
                "bunkers_count": total_bunkers,
                "water_count": total_waters,
                "viewer_filename": viewer_filename,
            })

        except Exception as e:
            logging.error("Failed to process course %s: %s", slug, e, exc_info=True)

    # Build and write index dashboard
    dashboard_html = build_dashboard_html(courses_summary)
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(dashboard_html)

    logging.info("Successfully generated portal dashboard at %s", index_path)
    print("\n" + "=" * 60)
    print(f"DASHBOARD CREATED: {index_path}")
    print(f"Total Course Viewers Available: {len(courses_summary)}")
    for c in courses_summary:
        print(f"  - {c['name']} ({c['hole_count']} holes) -> output/viewers/{c['viewer_filename']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Generate interactive HTML viewers and dashboard for all courses")
    parser.add_argument("--force", action="store_true", help="Force regenerate viewers even if they exist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    process_all_courses(force_regenerate=args.force)


if __name__ == "__main__":
    main()
