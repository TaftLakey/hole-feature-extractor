"""Unit tests for the site data pipeline, JSON schema validation, and atomic writer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from pydantic import ValidationError

from src.course_geometry import GolfCourse
from src.interactive_viewer import serialize_course_data
from src.schema import (
    CourseData,
    CoursesIndex,
    validate_course_data,
    validate_courses_index,
)
from scripts.build_site_data import (
    atomic_write_json,
    audit_course_quality,
    build_single_course,
)


class TestSiteDataPipeline(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        self.sample_geojson_path = self.fixtures_dir / "sample_course.geojson"

    def test_sample_course_serialization_and_schema_validity(self):
        """serialize_course_data produces valid data conforming to CourseData schema."""
        course = GolfCourse.from_geojson(self.sample_geojson_path)
        data = serialize_course_data(course)

        # 1. Schema validation on synthetic fixture (1 hole)
        validated = validate_course_data(data)
        self.assertIsInstance(validated, CourseData)
        self.assertEqual(len(validated.holes), 1)

        # 2. Check full 18-hole course serialization on Augusta National
        augusta_path = Path(__file__).resolve().parents[1] / "data" / "courses" / "augusta_national_golf_club.geojson"
        if augusta_path.exists():
            augusta_course = GolfCourse.from_geojson(augusta_path)
            augusta_data = serialize_course_data(augusta_course)
            augusta_validated = validate_course_data(augusta_data)
            self.assertEqual(len(augusta_validated.holes), 18)
            self.assertGreater(augusta_validated.total_yards, 7000)
            self.assertEqual(augusta_validated.total_par, 72)

        # 3. Rotation check: in Hole-Up view (SVG inverted Y), Pin should be at or near top (lower Y than Tee)
        for h in validated.holes:
            pin_y = h.pin.hole_up.y
            tee_y = h.tee.hole_up.y
            # In inverted SVG Y coordinates, "above" (further down the hole) means smaller Y
            self.assertLess(
                pin_y,
                tee_y,
                f"Hole {h.number}: expected pin Y ({pin_y}) < tee Y ({tee_y}) in hole-up view",
            )

        # 4. Bounds check: hole bounds contain pin and tee
        for h in validated.holes:
            bx, by, bw, bh = h.bounds_hole_up
            pin_x, pin_y = h.pin.hole_up.x, h.pin.hole_up.y
            tee_x, tee_y = h.tee.hole_up.x, h.tee.hole_up.y

            self.assertTrue(bx <= pin_x <= bx + bw, f"Hole {h.number}: pin X out of bounds")
            self.assertTrue(by <= pin_y <= by + bh, f"Hole {h.number}: pin Y out of bounds")
            self.assertTrue(bx <= tee_x <= bx + bw, f"Hole {h.number}: tee X out of bounds")
            self.assertTrue(by <= tee_y <= by + bh, f"Hole {h.number}: tee Y out of bounds")

    def test_schema_validation_rejects_invalid_data(self):
        """validate_course_data raises ValidationError on malformed or missing fields."""
        with self.assertRaises(ValidationError):
            validate_course_data({"course_name": "Incomplete Course"})

        # Invalid bounds (needs 4 elements)
        invalid_data = {
            "course_name": "Test",
            "total_holes": 1,
            "total_par": 4,
            "total_yards": 400,
            "overview": {"bounds": [0.0, 0.0]},  # only 2 elements
            "holes": [],
        }
        with self.assertRaises(ValidationError):
            validate_course_data(invalid_data)

    def test_courses_index_schema_validity(self):
        """CoursesIndex validates correct structure and attribution."""
        payload = {
            "schema_version": "1.0.0",
            "generated_at": "2026-11-09T10:00:00Z",
            "data_attribution": {
                "name": "OpenStreetMap contributors",
                "url": "https://www.openstreetmap.org/copyright",
                "license": "ODbL 1.0",
            },
            "courses": [
                {
                    "slug": "sample_course",
                    "name": "Sample Golf Club",
                    "holes": 18,
                    "par": 72,
                    "yards": 7200,
                    "tournaments": ["Sample Open"],
                    "data_file": "courses/sample_course.json",
                }
            ],
        }
        index = validate_courses_index(payload)
        self.assertIsInstance(index, CoursesIndex)
        self.assertEqual(len(index.courses), 1)
        self.assertEqual(index.courses[0].slug, "sample_course")

    def test_audit_course_quality_detects_defects(self):
        """audit_course_quality warns loudly on holes missing green, pin, tee, or centerline."""
        defective = {
            "course_name": "Defective Course",
            "holes": [
                {
                    "number": 1,
                    "paths": {"hole_up": {"green": "", "tees": [], "fairways": [], "centerline": ""}},
                    "pin": {"hole_up": {"x": None, "y": None}},
                    "tee": {"hole_up": {"x": None, "y": None}},
                }
            ],
        }
        warnings = audit_course_quality(defective)
        self.assertTrue(any("only 1 holes" in w for w in warnings))
        self.assertTrue(any("Missing green" in w for w in warnings))
        self.assertTrue(any("Missing tee geometry" in w for w in warnings))
        self.assertTrue(any("Missing pin coordinates" in w for w in warnings))
        self.assertTrue(any("Missing centerline" in w for w in warnings))

    def test_atomic_write_does_not_leave_corrupt_files_on_failure(self):
        """atomic_write_json leaves no partial or corrupt file if an error occurs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_path = Path(tmp_dir) / "output.json"

            # Valid write succeeds
            atomic_write_json(target_path, {"test": "valid"})
            self.assertTrue(target_path.exists())

            # Corrupt object that cannot be JSON serialized
            class UnserializableObject:
                pass

            with self.assertRaises(TypeError):
                atomic_write_json(target_path, {"bad": UnserializableObject()})

            # Original valid file should still be preserved unmodified
            with open(target_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.assertEqual(content, {"test": "valid"})

            # No leftover temporary files
            temp_files = list(Path(tmp_dir).glob(".tmp_build_*"))
            self.assertEqual(len(temp_files), 0)


if __name__ == "__main__":
    unittest.main()
