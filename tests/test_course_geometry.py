"""Unit tests for GolfCourse, GolfHole, Bunker, WaterHazard and coordinate checks."""

import json
import os
from pathlib import Path
import unittest
from shapely.geometry import LineString, Point, Polygon

from src.course_geometry import (
    Bunker,
    Fairway,
    GolfCourse,
    GolfFeature,
    GolfHole,
    Green,
    Rough,
    TeeBox,
    WaterHazard,
)


class TestGolfGeometry(unittest.TestCase):
    def setUp(self):
        # A simple synthetic hole for testing
        # Tee box at (0, 0), Green at (0, 400), Fairway in between, Bunker at (20, 200), Water at (-30, 250)
        # Using simple local coordinates or geographic coordinates
        self.tee_geom = Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)])
        self.fairway_geom = Polygon([(-25, 10), (25, 10), (25, 380), (-25, 380)])
        self.green_geom = Polygon([(-15, 385), (15, 385), (15, 415), (-15, 415)])
        self.bunker_geom = Polygon([(15, 190), (30, 190), (30, 210), (15, 210)])
        self.water_geom = Polygon([(-40, 240), (-20, 240), (-20, 270), (-40, 270)])
        self.centerline = LineString([(0, 0), (0, 200), (0, 400)])

        self.bunker = Bunker(
            id="b1",
            geometry=self.bunker_geom,
            name="Fairway Bunker Right",
            bunker_type="fairway",
            hole_ref=1,
        )
        self.water = WaterHazard(
            id="w1",
            geometry=self.water_geom,
            name="Left Pond",
            hazard_type="lateral_water_hazard",
            hole_ref=1,
        )
        self.tee = TeeBox(
            id="t1",
            geometry=self.tee_geom,
            tee_type="championship",
            hole_ref=1,
        )
        self.fairway = Fairway(
            id="f1",
            geometry=self.fairway_geom,
            hole_ref=1,
        )
        self.green = Green(
            id="g1",
            geometry=self.green_geom,
            pin=Point(0, 400),
            hole_ref=1,
        )

        self.hole = GolfHole(
            hole_number=1,
            name="Starter Hole",
            par=4,
            handicap=5,
            course_name="Test National",
            centerline=self.centerline,
            pin=Point(0, 400),
            tee_boxes=[self.tee],
            fairways=[self.fairway],
            green=self.green,
            bunkers=[self.bunker],
            water_hazards=[self.water],
        )

    def test_bunker_detection(self):
        # Point inside bunker (20, 200)
        hit_bunker = self.hole.is_in_bunker((20, 200))
        self.assertIsNotNone(hit_bunker)
        self.assertEqual(hit_bunker.id, "b1")
        self.assertEqual(hit_bunker.bunker_type, "fairway")
        self.assertEqual(self.hole.get_surface_type((20, 200)), "bunker")

        # Point outside bunker
        miss = self.hole.is_in_bunker((0, 200))
        self.assertIsNone(miss)

    def test_water_hazard_detection(self):
        # Point inside water (-30, 250)
        hit_water = self.hole.is_in_water((-30, 250))
        self.assertIsNotNone(hit_water)
        self.assertEqual(hit_water.id, "w1")
        self.assertEqual(self.hole.get_surface_type((-30, 250)), "water")

        # Point outside water
        self.assertIsNone(self.hole.is_in_water((0, 250)))

    def test_green_and_fairway_detection(self):
        # Green center
        self.assertTrue(self.hole.is_in_green((0, 400)))
        self.assertEqual(self.hole.get_surface_type((0, 400)), "green")

        # Fairway center
        self.assertTrue(self.hole.is_in_fairway((0, 100)))
        self.assertEqual(self.hole.get_surface_type((0, 100)), "fairway")

        # Tee box
        self.assertIsNotNone(self.hole.is_in_tee((0, 0)))
        self.assertEqual(self.hole.get_surface_type((0, 0)), "tee")

        # Out of bounds
        self.assertEqual(self.hole.get_surface_type((500, 500)), "out_of_bounds")

    def test_image_generation(self):
        img = self.hole.generate_image(dpi=72)
        self.assertIsNotNone(img)
        self.assertGreater(img.size[0], 100)
        self.assertGreater(img.size[1], 100)

    def test_coordinate_normalization(self):
        from src.course_geometry import _normalize_point

        p1 = _normalize_point({"lat": 33.5, "lng": -82.0})
        self.assertAlmostEqual(p1.x, -82.0)
        self.assertAlmostEqual(p1.y, 33.5)

        p2 = _normalize_point({"lat": 33.5, "lon": -82.0})
        self.assertAlmostEqual(p2.x, -82.0)
        self.assertAlmostEqual(p2.y, 33.5)

    def test_geojson_fixture_ingest(self):
        from pathlib import Path

        fixture_path = Path(__file__).parent / "fixtures" / "sample_course.geojson"
        self.assertTrue(fixture_path.exists(), f"Fixture file not found: {fixture_path}")

        course = GolfCourse.from_geojson(fixture_path)
        self.assertEqual(course.name, "National Golf Club")
        self.assertIn(1, course.holes)

        h1 = course.get_hole(1)
        self.assertEqual(h1.hole_number, 1)
        self.assertEqual(h1.name, "Tea Olive")
        self.assertEqual(h1.par, 4)
        self.assertEqual(h1.handicap, "5")

        # Test hole components
        self.assertIsNotNone(h1.green)
        self.assertIsNotNone(h1.pin)
        self.assertGreater(len(h1.tee_boxes), 0)
        self.assertGreater(len(h1.fairways), 0)
        self.assertEqual(len(h1.bunkers), 2)
        self.assertEqual(len(h1.water_hazards), 1)

        # Check bunker types
        types = {b.bunker_type for b in h1.bunkers}
        self.assertIn("fairway", types)
        self.assertIn("greenside", types)

        # Distance to pin from tee
        tee_pt = h1.tee_boxes[0].geometry.centroid
        dist = h1.distance_to_pin(tee_pt)
        self.assertGreater(dist, 400.0)

        # Image generation
        img = h1.generate_image(dpi=72)
        self.assertIsNotNone(img)

    def test_augusta_geojson_ingest(self):
        import os
        from pathlib import Path

        # Look in data/ directory or environment variable if provided by user
        candidates = [
            Path("data/augusta_national.geojson"),
            Path("data/augusta.geojson"),
        ]
        if "AUGUSTA_GEOJSON_PATH" in os.environ:
            candidates.insert(0, Path(os.environ["AUGUSTA_GEOJSON_PATH"]))

        geojson_path = None
        for cand in candidates:
            try:
                if cand.is_file():
                    geojson_path = cand
                    break
            except OSError:
                continue

        if geojson_path is None:
            # Skip if user has not placed full Augusta GeoJSON in data/
            return

        course = GolfCourse.from_geojson(geojson_path)
        self.assertEqual(len(course.holes), 18)
        self.assertIn("Augusta", course.name)

        # Test hole 1
        h1 = course.get_hole(1)
        self.assertEqual(h1.hole_number, 1)
        self.assertEqual(h1.par, 4)
        self.assertGreater(len(h1.bunkers), 0)

        # Test bunker detection with first bunker representative point
        b0 = h1.bunkers[0]
        pt = b0.geometry.representative_point()
        self.assertIsNotNone(h1.is_in_bunker(pt))
        self.assertEqual(h1.get_surface_type(pt), "bunker")

        # Test water hazard on Hole 13 (Rae's Creek)
        h13 = course.get_hole(13)
        self.assertGreater(len(h13.water_hazards), 0)
        w0 = h13.water_hazards[0]
        w_pt = w0.geometry.representative_point()
        self.assertIsNotNone(h13.is_in_water(w_pt))
        self.assertEqual(h13.get_surface_type(w_pt), "water")

        # Test that extra facilities (practice putting green, composite course, etc.)
        # were safely quarantined to unassigned_features and did not pollute the 18 holes
        self.assertGreater(len(course.unassigned_features), 0)
        unassigned_names = [f.name for f in course.unassigned_features if f.name]
        self.assertTrue(any("Practice" in n or "Replica" in n or "Composite" in n for n in unassigned_names))

    def test_nearby_course_spatial_outlier_filtering(self):
        """Features with ref=1 that are far away from Hole 1 centerline are rejected."""
        fixture_path = Path(__file__).parent / "fixtures" / "sample_course.geojson"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Inject an outlier feature: a bunker 2,000 yards away also tagged ref="1"
        data["features"].append({
            "type": "Feature",
            "properties": {
                "@id": "way/neighboring_course_bunker",
                "golf": "bunker",
                "ref": "1",
                "name": "Neighboring Course Bunker",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-82.050, 33.520],
                        [-82.049, 33.520],
                        [-82.049, 33.521],
                        [-82.050, 33.521],
                        [-82.050, 33.520],
                    ]
                ],
            },
        })

        course = GolfCourse.from_geojson(data, max_feature_distance_yards=350.0)
        h1 = course.get_hole(1)
        # Should NOT include the neighboring bunker in Hole 1
        bunker_ids = [b.id for b in h1.bunkers]
        self.assertNotIn("way/neighboring_course_bunker", bunker_ids)

        # But it should be in unassigned_features
        unassigned_ids = [u.id for u in course.unassigned_features]
        self.assertIn("way/neighboring_course_bunker", unassigned_ids)

    def test_interactive_html_export(self):
        import tempfile
        from src.interactive_viewer import export_interactive_html

        fixture_path = Path(__file__).parent / "fixtures" / "sample_course.geojson"
        course = GolfCourse.from_geojson(fixture_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_viewer.html"
            result_path = course.export_interactive_html(out_file)
            self.assertTrue(result_path.exists())
            self.assertGreater(result_path.stat().st_size, 5000)

            content = result_path.read_text(encoding="utf-8")
            self.assertIn("National Golf Club", content)
            self.assertIn("HOLE 1", content)
            self.assertIn("<svg", content)
            self.assertIn("shot-planner-card", content)


if __name__ == "__main__":
    unittest.main()
