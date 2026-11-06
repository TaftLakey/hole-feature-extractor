"""Build Course Registry from PGA Tour Leaderboard GraphQL responses.

Iterates over tournament IDs, downloads leaderboards via download_leaderboard
(if not already cached), and parses the course metadata to construct a rich,
canonical course registry (courses_registry.json).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Configure paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PGA_SCRAPER_ROOT = PROJECT_ROOT.parent / "taft-pga-scraper"
PGA_SCRAPER_SRC = PGA_SCRAPER_ROOT / "src"
PGA_NORMALIZED_DIR = PGA_SCRAPER_ROOT / "data" / "normalized"
PGA_REFERENCE_DIR = PGA_SCRAPER_ROOT / "data" / "reference"

# Add taft-pga-scraper/src to sys.path
sys.path.insert(0, str(PGA_SCRAPER_SRC))

try:
    from download_leaderboard import download_leaderboard
except ImportError as err:
    download_leaderboard = None  # type: ignore[assignment]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


TOURNAMENT_NAME_LOOKUP: dict[str, str] = {}
TOURNAMENT_URL_LOOKUP: dict[str, str] = {}


def init_tournament_lookups() -> None:
    """Populate tournament name and URL lookups from reference files."""
    global TOURNAMENT_NAME_LOOKUP, TOURNAMENT_URL_LOOKUP
    tournaments_file = PGA_REFERENCE_DIR / "tournaments.json"
    courses_ref_file = PGA_REFERENCE_DIR / "courses.json"

    if tournaments_file.exists():
        try:
            with open(tournaments_file, encoding="utf-8") as f:
                tdata = json.load(f)
            for code, meta in tdata.items():
                if isinstance(meta, dict):
                    TOURNAMENT_NAME_LOOKUP[code] = meta.get("name", "")
                    TOURNAMENT_URL_LOOKUP[code] = meta.get("url", "")
        except Exception as e:
            logging.warning("Could not read tournaments.json: %s", e)

    if courses_ref_file.exists():
        try:
            with open(courses_ref_file, encoding="utf-8") as f:
                cdata = json.load(f)
            for c_info in cdata.values():
                t_id = str(c_info.get("tournamentId") or "")
                t_name = str(c_info.get("tournamentName") or "")
                if t_id and len(t_id) >= 3:
                    code = t_id[-3:]
                    if t_name and code not in TOURNAMENT_NAME_LOOKUP:
                        TOURNAMENT_NAME_LOOKUP[code] = t_name
        except Exception as e:
            logging.warning("Could not read courses.json: %s", e)


def load_target_tournament_ids(
    year_filter: str | None = "2025",
    limit: int | None = None,
) -> list[str]:
    """Load tournament IDs from reference files in taft-pga-scraper."""
    tournaments_file = PGA_REFERENCE_DIR / "tournaments.json"
    queue_file = PGA_SCRAPER_ROOT / "data" / "scrape_reference" / "tournaments_ids.json"
    courses_ref_file = PGA_REFERENCE_DIR / "courses.json"

    tournament_ids: list[str] = []

    # Priority 1: Check existing courses.json in reference
    if courses_ref_file.exists():
        try:
            with open(courses_ref_file, encoding="utf-8") as f:
                cdata = json.load(f)
            for item in cdata.values():
                t_id = item.get("tournamentId")
                if t_id and (not year_filter or year_filter in t_id):
                    if t_id not in tournament_ids:
                        tournament_ids.append(t_id)
        except Exception as e:
            logging.warning("Could not read courses.json: %s", e)

    # Priority 2: Use queue_file if available
    if queue_file.exists():
        try:
            with open(queue_file, encoding="utf-8") as f:
                qdata = json.load(f)
            for t_id in qdata:
                if not year_filter or year_filter in t_id:
                    if t_id not in tournament_ids:
                        tournament_ids.append(t_id)
        except Exception as e:
            logging.warning("Could not read tournaments_ids.json: %s", e)

    # Priority 3: Construct from tournaments.json
    if not tournament_ids and tournaments_file.exists():
        try:
            with open(tournaments_file, encoding="utf-8") as f:
                tdata = json.load(f)
            year = year_filter or "2025"
            for code in tdata.keys():
                t_id = f"R{year}{code}"
                if t_id not in tournament_ids:
                    tournament_ids.append(t_id)
        except Exception as e:
            logging.warning("Could not read tournaments.json: %s", e)

    if limit and limit > 0:
        tournament_ids = tournament_ids[:limit]

    return tournament_ids


def get_leaderboard_payload(
    tournament_id: str,
    normalized_dir: Path = PGA_NORMALIZED_DIR,
    delay_sec: float = 1.0,
) -> dict[str, Any] | None:
    """Retrieve leaderboard JSON, downloading via download_leaderboard if missing."""
    normalized_dir.mkdir(parents=True, exist_ok=True)
    decoded_path = normalized_dir / f"{tournament_id}_leaderboard.json"

    if decoded_path.exists():
        try:
            with open(decoded_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("Failed to parse cached %s: %s. Re-downloading...", decoded_path.name, e)

    if download_leaderboard is None:
        logging.error("download_leaderboard function is not available.")
        return None

    logging.info("Downloading leaderboard for %s...", tournament_id)
    time.sleep(delay_sec)
    status = download_leaderboard(
        tournament=tournament_id,
        output_dir=normalized_dir,
        timeout=15.0,
    )
    if status != 0:
        logging.warning("Failed to download leaderboard for %s (exit code %s)", tournament_id, status)
        return None

    if decoded_path.exists():
        try:
            with open(decoded_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error("Error reading newly downloaded %s: %s", decoded_path.name, e)
            return None

    return None


def extract_tournament_courses(
    leaderboard: dict[str, Any],
    fallback_tournament_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract tournament metadata and list of courses from leaderboard."""
    tournament_id = leaderboard.get("tournamentId") or fallback_tournament_id
    tournament_name = (
        leaderboard.get("tournamentName")
        or leaderboard.get("name")
        or leaderboard.get("title")
        or ""
    )

    # Fallback to tournament lookup table if empty
    if not tournament_name:
        code = fallback_tournament_id[-3:] if len(fallback_tournament_id) >= 3 else ""
        tournament_name = TOURNAMENT_NAME_LOOKUP.get(code, "")


    raw_courses = leaderboard.get("courses", [])
    courses_found: list[dict[str, Any]] = []

    for c in raw_courses:
        if not isinstance(c, dict):
            continue
        c_id = str(c.get("id") or "").strip()
        c_name = str(c.get("courseName") or "").strip()
        c_code = str(c.get("courseCode") or "").strip()
        scoring_level = str(c.get("scoringLevel") or "").strip()
        is_host = bool(c.get("hostCourse", False))

        if not c_name:
            continue

        courses_found.append({
            "course_id": c_id,
            "course_name": c_name,
            "course_code": c_code,
            "scoring_level": scoring_level,
            "host_course": is_host,
        })

    t_meta = {
        "tournament_id": tournament_id,
        "tournament_name": tournament_name,
        "round_header": leaderboard.get("leaderboardRoundHeader"),
        "status": leaderboard.get("tournamentStatus"),
        "course_count": len(courses_found),
    }

    return t_meta, courses_found


def build_registry(
    tournament_ids: list[str],
    delay_sec: float = 1.0,
) -> dict[str, Any]:
    """Build course and tournament registry from leaderboard data."""
    courses_by_name: dict[str, dict[str, Any]] = {}
    courses_by_id: dict[str, dict[str, Any]] = {}
    tournaments_map: dict[str, dict[str, Any]] = {}

    success_count = 0
    fail_count = 0

    total = len(tournament_ids)
    logging.info("Building course registry for %d tournaments...", total)

    for i, t_id in enumerate(tournament_ids, 1):
        logging.info("[%d/%d] Processing %s...", i, total, t_id)
        data = get_leaderboard_payload(t_id, delay_sec=delay_sec)
        if not data:
            fail_count += 1
            continue

        t_meta, courses = extract_tournament_courses(data, t_id)
        tournaments_map[t_id] = {
            **t_meta,
            "courses": courses,
        }
        success_count += 1

        for c in courses:
            c_name = c["course_name"]
            c_id = c["course_id"]

            if c_name not in courses_by_name:
                courses_by_name[c_name] = {
                    "course_name": c_name,
                    "course_id": c_id,
                    "course_code": c["course_code"],
                    "scoring_level": c["scoring_level"],
                    "tournaments": [],
                }

            # Update ID if missing
            if not courses_by_name[c_name]["course_id"] and c_id:
                courses_by_name[c_name]["course_id"] = c_id

            # Add tournament record
            t_record = {
                "tournament_id": t_id,
                "tournament_name": t_meta["tournament_name"],
                "host_course": c["host_course"],
            }
            if t_record not in courses_by_name[c_name]["tournaments"]:
                courses_by_name[c_name]["tournaments"].append(t_record)

            if c_id:
                courses_by_id[c_id] = courses_by_name[c_name]

    registry = {
        "metadata": {
            "total_tournaments_processed": total,
            "successful_tournaments": success_count,
            "failed_tournaments": fail_count,
            "total_unique_courses": len(courses_by_name),
        },
        "courses": courses_by_name,
        "courses_by_id": courses_by_id,
        "tournaments": tournaments_map,
    }

    return registry


def main():
    parser = argparse.ArgumentParser(description="Build PGA Tour course registry from leaderboards")
    parser.add_argument("--year", default="2025", help="Year filter for tournaments (default: 2025, or 'all')")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tournaments to process")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between API calls (default: 1.0)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: data/courses_registry.json)")
    args = parser.parse_args()

    init_tournament_lookups()
    year_filter = None if args.year.lower() == "all" else args.year
    t_ids = load_target_tournament_ids(year_filter=year_filter, limit=args.limit)

    if not t_ids:
        logging.error("No tournament IDs found matching year=%s", args.year)
        sys.exit(1)

    registry = build_registry(t_ids, delay_sec=args.delay)

    output_path = Path(args.output) if args.output else DATA_DIR / "courses_registry.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    # Also save copy to taft-pga-scraper/data/reference/courses_registry.json if accessible
    try:
        pga_copy_path = PGA_REFERENCE_DIR / "courses_registry.json"
        pga_copy_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pga_copy_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
        logging.info("Also updated %s", pga_copy_path)
    except Exception as e:
        logging.warning("Could not write copy to %s: %s", PGA_REFERENCE_DIR, e)

    logging.info("Saved course registry to %s", output_path)
    print(f"\nRegistry Summary:")
    print(f"  Tournaments checked: {registry['metadata']['total_tournaments_processed']}")
    print(f"  Successful:          {registry['metadata']['successful_tournaments']}")
    print(f"  Failed / No Data:    {registry['metadata']['failed_tournaments']}")
    print(f"  Unique Courses:      {registry['metadata']['total_unique_courses']}")



if __name__ == "__main__":
    main()
