# Adding a Golf Course to the Web App

This guide explains how to add or update a golf course in the viewer using the offline Python build pipeline.

---

## 1. Prerequisites

From the repository root, ensure your environment has the required dependencies:

```bash
# Install Python pipeline dependencies
pip install -r requirements.txt

# Install frontend web dependencies
cd web
npm install
cd ..
```

---

## 2. One-Command Course Pipeline

To add a new course, run `build_site_data.py` with the course name, PGA course ID, or tournament ID:

```bash
# Add or refresh a course by name
python pipeline/scripts/build_site_data.py "Quail Hollow Club"

# Re-download fresh OSM data from Overpass (bypassing local cache)
python pipeline/scripts/build_site_data.py "TPC Sawgrass" --force

# Rebuild all cached course GeoJSON files in pipeline/data/
python pipeline/scripts/build_site_data.py --all
```

### What the Command Does
1. Resolves course geographical bounds using Nominatim/Overpass (or reuses local cache in `pipeline/data/courses/<slug>.geojson`).
2. Builds the `GolfCourse` domain geometry model and serializes all Hole-Up and North-Up vector layers.
3. Cleans metadata (attaches tournament names from `courses_registry.json` while excluding internal IDs and scoring levels).
4. Runs an automated **Data Quality Audit**.
5. Validates against the strict Pydantic JSON schema.
6. Atomically writes `web/public/data/courses/<slug>.json` using a temporary file and atomic rename.
7. Rebuilds and validates the master index at `web/public/data/courses.json`.

---

## 3. Understanding Data Quality Warnings

When building a course, the auditor prints warnings if defects are detected in the OSM source data:

| Warning | Meaning | Resolution |
|---|---|---|
| `Course has only N holes (expected 18)` | Fewer than 18 holes were mapped in OSM. | Verify OSM tagging for missing hole relations/ways. |
| `Hole N: Missing green geometry` | No `golf=green` was detected near hole N. | Add `golf=green` tagged polygon in OpenStreetMap. |
| `Hole N: Missing tee geometry` | No `golf=tee` or tee box was detected. | Add `golf=tee` polygon or tee marker in OSM. |
| `Hole N: Missing pin coordinates` | Pin point was not detected or placed. | Place flag/pin position or green centroid in OSM. |
| `Hole N: Missing centerline geometry` | No hole centerline or hole relation found. | Draw centerline or create OSM hole relation. |

---

## 4. Previewing Locally

Once the data is generated, test the course in the React application:

```bash
cd web
npm run dev
```

Open `http://localhost:5173` in your browser. Verify:
- The new course appears on the dashboard card grid.
- All 18 holes render cleanly with fairways, greens, tees, bunkers, and water.
- Hole-Up and North-Up toggling works as expected.
- The shot planner places and calculates distances correctly.

---

## 5. Running Verification Tests

Run both test suites before pushing your changes:

```bash
# Run Python pipeline tests
python -m unittest discover pipeline/tests

# Run React frontend tests
cd web
npm test
npm run build
```

---

## 6. Commit and Deploy

Commit the newly generated course data files:

```bash
git add pipeline/data/courses/<slug>.geojson
git add web/public/data/courses/<slug>.json
git add web/public/data/courses.json
git commit -m "feat(courses): add <course_name>"
git push origin main
```

The GitHub Actions CI/CD workflow automatically builds the static bundle and deploys it to GitHub Pages.
