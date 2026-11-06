# Hole Feature Extractor

Geographical feature parser and visualization engine for golf courses. Ingests OpenStreetMap (OSM) / Overpass Turbo GeoJSON datasets into rich domain models (`GolfCourse`, `GolfHole`, `Bunker`, `WaterHazard`, `Green`, `TeeBox`, `Fairway`, `Rough`).

## Features

- **Automated Ingestion**: Parses standard GeoJSON features and groups them by hole reference into structured Python objects.
- **Surface & Hazard Detection**: Fast point-in-polygon queries for lie identification (`green`, `fairway`, `tee`, `bunker`, `water`, `rough`, `out_of_bounds`).
- **Yardage & Geodesic Calculations**: Local transverse Mercator projections to measure accurate distances in yards to the pin, hazards, and fairway corridors.
- **Overhead Yardage Book Rendering**: Generates high-resolution 2D yardage book graphics oriented with tee-at-bottom and green-at-top, including yardage arcs and hazard highlights.
- **CLI Interface**: Inspect hole details or bulk export 18-hole yardage book image assets.

## Installation

```bash
pip install -r requirements.txt
```

Core dependencies:
- `shapely >= 2.0.0`
- `pyproj >= 3.5.0`
- `matplotlib >= 3.7.0`
- `pillow >= 9.5.0`
- `requests >= 2.28.0`
- `osm2geojson >= 0.3.0`

## Automated Course Downloader & Registry

Download golf course features directly from OpenStreetMap using the course name, PGA Course ID, or Tournament ID:

```bash
# Download by official course name
python src/course_downloader.py "TPC Sawgrass"

# Download by course ID or tournament ID (uses courses_registry.json)
python src/course_downloader.py 011
python src/course_downloader.py R2025005

# Download and export interactive HTML viewer in one command
python src/course_downloader.py "Quail Hollow Club" --export-html ./output/quail_hollow.html
```

To sync the tournament-to-course registry from PGA Tour compressed leaderboards:

```bash
python src/build_courses_registry.py --year 2025
```

## CLI Usage

### Inspect a Course or Specific Hole

```bash
# Print summary of all holes
python -m src path/to/course.geojson

# Inspect a single hole in detail
python -m src path/to/course.geojson --hole 1

# Filter by course name if multiple courses are present in the GeoJSON
python -m src path/to/course.geojson --course-name "Augusta National"
```

### Export Interactive Viewer & Overhead Yardage Book Images

```bash
# Export standalone interactive vector HTML viewer
python -m src path/to/course.geojson --export-html ./output/course_interactive.html

# Export overhead yardage book PNG images
python -m src path/to/course.geojson --export-images ./output --dpi 200
```

## Python API Usage

```python
from src.course_geometry import GolfCourse

# 1. Ingest course GeoJSON
course = GolfCourse.from_geojson("tests/fixtures/sample_course.geojson")
print(f"Course: {course.name}, Holes: {len(course.holes)}")

# 2. Get specific hole
hole = course.get_hole(1)
print(f"Hole 1: Par {hole.par}, {hole.length_yards} yards")

# 3. Check surface lie & hazard containment
coords = (-82.0200, 33.5040)  # (lon, lat) or dict {"lat": 33.504, "lng": -82.020}
lie = hole.get_surface_type(coords)
dist_to_pin = hole.distance_to_pin(coords)
print(f"Lie: {lie}, Distance to pin: {dist_to_pin} yards")

# 4. Generate & save yardage book image
img = hole.generate_image(dpi=200, rotated=True)
hole.save_image("output/hole_01.png")
```

## Running Tests

```bash
python -m unittest discover tests
```
