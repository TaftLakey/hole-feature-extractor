"""Golf Course and Golf Hole Geometry Representation and Visualization.

Parses GeoJSON geographical features of golf courses into domain models
(GolfCourse, GolfHole, Bunker, WaterHazard, Green, TeeBox, Fairway, Rough),
supports coordinate boundary checks (point-in-polygon), distance calculations
in yards, and generates high-resolution overhead yardage book imagery.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence, Union

# Set Matplotlib cache dir if needed to avoid permission warnings on Windows
if "MPLCONFIGDIR" not in os.environ:
    import tempfile
    os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib-cache")

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from PIL import Image
import pyproj
from shapely.affinity import rotate, scale, translate
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union


def _extract_polygons(geom: Any) -> Optional[Union[Polygon, MultiPolygon]]:
    """Extract valid Polygon or MultiPolygon geometries from any Shapely result."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    if hasattr(geom, "geoms"):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not polys:
            return None
        if len(polys) == 1:
            return polys[0]
        return MultiPolygon(polys)
    return None


def _normalize_point(coords: Any, lat_first: Optional[bool] = None) -> Point:
    """Convert various coordinate representations into a Shapely Point(lon, lat).

    Supports:
      - Point(lon, lat)
      - (lat, lon) or (lon, lat) tuples / lists
      - dict with keys ('lat', 'lon'), ('latitude', 'longitude'), or ('x', 'y')
    """
    if isinstance(coords, Point):
        return coords

    if isinstance(coords, dict):
        if "lon" in coords and "lat" in coords:
            return Point(float(coords["lon"]), float(coords["lat"]))
        if "lng" in coords and "lat" in coords:
            return Point(float(coords["lng"]), float(coords["lat"]))
        if "longitude" in coords and "latitude" in coords:
            return Point(float(coords["longitude"]), float(coords["latitude"]))
        if "x" in coords and "y" in coords:
            return Point(float(coords["x"]), float(coords["y"]))

    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        val1 = float(coords[0])
        val2 = float(coords[1])

        if lat_first is True:
            return Point(val2, val1)
        if lat_first is False:
            return Point(val1, val2)

        # Smart detection for Western Hemisphere / US coordinates:
        # e.g., val1=33.5, val2=-82.0 -> lat=33.5, lon=-82.0 -> Point(-82.0, 33.5)
        if -90 <= val1 <= 90 and (-180 <= val2 <= 180) and val2 < 0 and val1 > 0:
            return Point(val2, val1)
        # Or if val1 is lon (< 0) and val2 is lat (> 0):
        if val1 < 0 and val2 > 0 and -90 <= val2 <= 90:
            return Point(val1, val2)

        # Fallback to standard (lon, lat) / (x, y)
        return Point(val1, val2)

    raise ValueError(f"Unable to parse coordinates from: {coords}")


def _build_yards_transformer(center_lon: float, center_lat: float) -> tuple[Optional[pyproj.Transformer], Optional[pyproj.Transformer], str]:
    """Build forward and inverse pyproj transformers for a local yard-based transverse Mercator projection.

    If coordinates are non-geographic (e.g. |lat| > 90 or |lon| > 180), returns None to indicate planar coords.
    """
    if abs(center_lat) > 90.0 or abs(center_lon) > 180.0:
        return None, None, "PLANAR_LOCAL"

    crs_wgs = "EPSG:4326"
    crs_yards = f"+proj=tmerc +lat_0={center_lat} +lon_0={center_lon} +units=us-yd +ellps=WGS84"
    to_yards = pyproj.Transformer.from_crs(crs_wgs, crs_yards, always_xy=True)
    to_wgs = pyproj.Transformer.from_crs(crs_yards, crs_wgs, always_xy=True)
    return to_yards, to_wgs, crs_yards


# ==============================================================================
# Golf Feature Base & Specialized Subclasses
# ==============================================================================

@dataclass
class GolfFeature:
    """Base class for any golf course geographical feature."""
    id: str
    geometry: BaseGeometry
    name: Optional[str] = None
    description: Optional[str] = None
    surface: Optional[str] = None
    hole_ref: Optional[int] = None
    properties: dict[str, Any] = field(default_factory=dict)

    def contains(self, coords: Any, lat_first: Optional[bool] = None) -> bool:
        """Check whether the given coordinates fall inside this feature."""
        pt = _normalize_point(coords, lat_first=lat_first)
        return self.geometry.contains(pt)

    def distance_yards(
        self,
        coords: Any,
        transformer: Optional[pyproj.Transformer] = None,
        lat_first: Optional[bool] = None,
    ) -> float:
        """Compute the distance from coordinates to this feature in yards."""
        pt = _normalize_point(coords, lat_first=lat_first)
        if transformer is None:
            c = self.geometry.centroid
            t_forward, _, _ = _build_yards_transformer(c.x, c.y)
            transformer = t_forward

        if transformer is not None:
            pt_yd = transform(transformer.transform, pt)
            geom_yd = transform(transformer.transform, self.geometry)
            return float(geom_yd.distance(pt_yd))
        return float(self.geometry.distance(pt))


@dataclass
class Bunker(GolfFeature):
    """Represents a sand bunker hazard on a golf hole."""
    bunker_type: str = "general"  # "greenside", "fairway", or "general"
    natural: str = "sand"


@dataclass
class WaterHazard(GolfFeature):
    """Represents a water hazard or lateral water hazard."""
    hazard_type: str = "water_hazard"  # "lateral_water_hazard", "water_hazard", "creek", "pond"
    natural: str = "water"


@dataclass
class Green(GolfFeature):
    """Represents the putting green surface."""
    surface: str = "grass"
    pin: Optional[Point] = None


@dataclass
class TeeBox(GolfFeature):
    """Represents a tee box or teeing ground."""
    tee_type: str = "standard"  # "championship", "tournament", "member", "forward"
    surface: str = "grass"


@dataclass
class Fairway(GolfFeature):
    """Represents a fairway surface."""
    surface: str = "grass"


@dataclass
class Rough(GolfFeature):
    """Represents a rough surface."""
    surface: str = "grass"


# ==============================================================================
# Golf Hole Class
# ==============================================================================

class GolfHole:
    """Represents a single golf hole with all its constituent features and queries."""

    def __init__(
        self,
        hole_number: int,
        name: Optional[str] = None,
        par: int = 4,
        handicap: Optional[Union[int, str]] = None,
        course_name: Optional[str] = None,
        description: Optional[str] = None,
        centerline: Optional[LineString] = None,
        pin: Optional[Point] = None,
        tee_boxes: Optional[list[TeeBox]] = None,
        fairways: Optional[list[Fairway]] = None,
        green: Optional[Green] = None,
        bunkers: Optional[list[Bunker]] = None,
        water_hazards: Optional[list[WaterHazard]] = None,
        rough: Optional[list[Rough]] = None,
    ) -> None:
        self.hole_number = hole_number
        self.name = name or f"Hole {hole_number}"
        self.par = int(par)
        self.handicap = handicap
        self.course_name = course_name or "Unknown Course"
        self.description = description
        self.centerline = centerline
        self.tee_boxes = tee_boxes or []
        self.fairways = fairways or []
        self.green = green
        self.bunkers = bunkers or []
        self.water_hazards = water_hazards or []
        self.rough = rough or []

        # Determine Pin position
        if pin is not None:
            self.pin = pin
        elif self.green and self.green.pin:
            self.pin = self.green.pin
        elif self.green:
            self.pin = self.green.geometry.centroid
        elif self.centerline and len(self.centerline.coords) > 0:
            self.pin = Point(self.centerline.coords[-1])
        else:
            self.pin = None

        # Determine Tee position
        if self.tee_boxes:
            # Prefer championship / tournament tee, otherwise first tee
            champ_tees = [t for t in self.tee_boxes if "champ" in (t.tee_type or "").lower()]
            active_tee = champ_tees[0] if champ_tees else self.tee_boxes[0]
            self.tee_point: Optional[Point] = active_tee.geometry.centroid
        elif self.centerline and len(self.centerline.coords) > 0:
            self.tee_point = Point(self.centerline.coords[0])
        else:
            self.tee_point = None

        # Setup local yards projection transformer
        ref_pt = self.pin or self.tee_point or (Point(self.centerline.coords[0]) if self.centerline else Point(0, 0))
        self._to_yards, self._to_wgs, self.crs_local = _build_yards_transformer(ref_pt.x, ref_pt.y)

        # Calculate hole length in yards along centerline (or direct tee-to-pin)
        def _to_yd_init(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
            if geom is None or geom.is_empty:
                return None
            return transform(self._to_yards.transform, geom) if self._to_yards else geom

        if self.centerline is not None and len(self.centerline.coords) >= 2:
            cl_yd = _to_yd_init(self.centerline)
            self.length_yards = round(float(cl_yd.length), 1) if cl_yd else 0.0
        elif self.tee_point and self.pin:
            p_tee_yd = _to_yd_init(self.tee_point)
            p_pin_yd = _to_yd_init(self.pin)
            self.length_yards = round(float(p_tee_yd.distance(p_pin_yd)), 1) if p_tee_yd and p_pin_yd else 0.0
        else:
            self.length_yards = 0.0

        if self.green is None:
            self._resolve_green()

        self._image_cache: Optional[Image.Image] = None

    def _resolve_green(self) -> None:
        """Resolve the green for this hole using fairway relation inner cutouts or tight cap."""
        if self.pin is None or self._to_wgs is None:
            return

        def _to_yd(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
            if geom is None or geom.is_empty:
                return None
            return transform(self._to_yards.transform, geom) if self._to_yards else geom

        pin_yd = _to_yd(self.pin)
        if not pin_yd:
            return

        best_inner_poly = None
        best_inner_wgs = None

        # 1. Search for authentic green cutout inside fairway relation interiors
        for fw in self.fairways:
            geoms = fw.geometry.geoms if hasattr(fw.geometry, 'geoms') else [fw.geometry]
            for poly in geoms:
                if hasattr(poly, 'interiors') and poly.interiors:
                    for interior in poly.interiors:
                        hp_wgs = Polygon(interior)
                        hp_yd = _to_yd(hp_wgs)
                        if hp_yd and not hp_yd.is_empty:
                            if hp_yd.contains(pin_yd):
                                best_inner_poly = hp_yd
                                best_inner_wgs = hp_wgs
                                break
                            elif hp_yd.distance(pin_yd) <= 15.0 and (hp_yd.area * 9.0) >= 1500.0:
                                if best_inner_poly is None or hp_yd.distance(pin_yd) < best_inner_poly.distance(pin_yd):
                                    best_inner_poly = hp_yd
                                    best_inner_wgs = hp_wgs
                    if best_inner_poly and best_inner_poly.contains(pin_yd):
                        break
                if best_inner_poly and best_inner_poly.contains(pin_yd):
                    break

        if best_inner_wgs is not None:
            self.green = Green(
                id=f"osm_inner_green_{self.hole_number}",
                geometry=best_inner_wgs,
                name=f"Hole {self.hole_number} Green",
                description="Authentic green extracted from fairway relation cutout",
                surface="grass",
                hole_ref=self.hole_number,
                pin=self.pin,
                properties={"extracted_from_fairway_relation": True},
            )
            return

        # 2. Fallback: Tight localized green cap around the pin (strictly bounded)
        tight_cap = pin_yd.buffer(16.0, quad_segs=16)

        fw_geoms = [_to_yd(f.geometry) for f in self.fairways if f.geometry]
        if fw_geoms:
            fw_union = unary_union([g for g in fw_geoms if g and not g.is_empty])
            if fw_union and not fw_union.is_empty and tight_cap.intersects(fw_union):
                diff = tight_cap.difference(fw_union)
                extracted = _extract_polygons(diff)
                if extracted and not extracted.is_empty:
                    polys = list(extracted.geoms) if isinstance(extracted, MultiPolygon) else [extracted]
                    p_candidates = [p for p in polys if p.contains(pin_yd) or p.distance(pin_yd) <= 15.0]
                    if p_candidates:
                        tight_cap = min(p_candidates, key=lambda p: p.distance(pin_yd))

        b_geoms = [_to_yd(b.geometry) for b in self.bunkers if b.geometry]
        if b_geoms:
            b_union = unary_union([g for g in b_geoms if g and not g.is_empty])
            if b_union and not b_union.is_empty and tight_cap.intersects(b_union):
                punched = tight_cap.difference(b_union.buffer(0.3))
                punched_poly = _extract_polygons(punched)
                if punched_poly and not punched_poly.is_empty:
                    p_list = list(punched_poly.geoms) if isinstance(punched_poly, MultiPolygon) else [punched_poly]
                    p_candidates = [p for p in p_list if p.contains(pin_yd) or p.distance(pin_yd) <= 15.0]
                    if p_candidates:
                        tight_cap = min(p_candidates, key=lambda p: p.distance(pin_yd))

        cleaned_poly = tight_cap.buffer(1.5, join_style=1).buffer(-1.5, join_style=1)
        if cleaned_poly and not cleaned_poly.is_empty and isinstance(cleaned_poly, (Polygon, MultiPolygon)):
            tight_cap = cleaned_poly

        green_wgs = transform(self._to_wgs.transform, tight_cap)
        self.green = Green(
            id=f"synth_green_{self.hole_number}",
            geometry=green_wgs,
            name=f"Hole {self.hole_number} Green",
            description="Procedural tight green cap",
            surface="grass",
            hole_ref=self.hole_number,
            pin=self.pin,
            properties={"synthetic": True, "method": "tight_cap"},
        )

        self._image_cache: Optional[Image.Image] = None

    # --------------------------------------------------------------------------
    # Boundary and Coordinate Checking Methods
    # --------------------------------------------------------------------------

    def is_in_bunker(self, coords: Any, lat_first: Optional[bool] = None) -> Optional[Bunker]:
        """Check if coordinates fall inside any bunker on this hole.

        Returns the matching Bunker object, or None.
        """
        pt = _normalize_point(coords, lat_first=lat_first)
        for b in self.bunkers:
            if b.geometry.contains(pt):
                return b
        return None

    def is_in_water(self, coords: Any, lat_first: Optional[bool] = None) -> Optional[WaterHazard]:
        """Check if coordinates fall inside any water hazard on this hole.

        Returns the matching WaterHazard object, or None.
        """
        pt = _normalize_point(coords, lat_first=lat_first)
        for w in self.water_hazards:
            if w.geometry.contains(pt):
                return w
        return None

    def is_in_green(self, coords: Any, lat_first: Optional[bool] = None) -> bool:
        """Check if coordinates fall on the green."""
        if not self.green:
            return False
        pt = _normalize_point(coords, lat_first=lat_first)
        return self.green.geometry.contains(pt)

    def is_in_fairway(self, coords: Any, lat_first: Optional[bool] = None) -> bool:
        """Check if coordinates fall on any fairway polygon for this hole."""
        pt = _normalize_point(coords, lat_first=lat_first)
        return any(f.geometry.contains(pt) for f in self.fairways)

    def is_in_tee(self, coords: Any, lat_first: Optional[bool] = None) -> Optional[TeeBox]:
        """Check if coordinates fall on a tee box for this hole."""
        pt = _normalize_point(coords, lat_first=lat_first)
        for t in self.tee_boxes:
            if t.geometry.contains(pt):
                return t
        return None

    def is_in_rough(self, coords: Any, lat_first: Optional[bool] = None) -> bool:
        """Check if coordinates fall in the rough of this hole."""
        pt = _normalize_point(coords, lat_first=lat_first)
        return any(r.geometry.contains(pt) for r in self.rough)

    def get_surface_type(self, coords: Any, lat_first: Optional[bool] = None) -> str:
        """Determine surface lie type for given coordinates.

        Returns one of: 'bunker', 'water', 'green', 'tee', 'fairway', 'rough', 'out_of_bounds'.
        """
        pt = _normalize_point(coords, lat_first=lat_first)

        if self.is_in_bunker(pt):
            return "bunker"
        if self.is_in_water(pt):
            return "water"
        if self.is_in_green(pt):
            return "green"
        if self.is_in_tee(pt):
            return "tee"
        if self.is_in_fairway(pt):
            return "fairway"
        if self.is_in_rough(pt):
            return "rough"

        return "out_of_bounds"

    def distance_to_pin(self, coords: Any, lat_first: Optional[bool] = None) -> float:
        """Calculate distance in yards from given coordinates to the pin."""
        if self.pin is None:
            return 0.0
        pt = _normalize_point(coords, lat_first=lat_first)
        if self._to_yards is not None:
            pt_yd = transform(self._to_yards.transform, pt)
            pin_yd = transform(self._to_yards.transform, self.pin)
            return round(float(pt_yd.distance(pin_yd)), 1)
        return round(float(pt.distance(self.pin)), 1)

    def distance_to_hazard(self, coords: Any, hazard: GolfFeature, lat_first: Optional[bool] = None) -> float:
        """Calculate distance in yards to a specific hazard or feature."""
        return hazard.distance_yards(coords, transformer=self._to_yards, lat_first=lat_first)

    # --------------------------------------------------------------------------
    # Image Generation & Visualization
    # --------------------------------------------------------------------------

    @property
    def image(self) -> Image.Image:
        """Lazy-loaded cached PIL Image rendering of the hole."""
        if self._image_cache is None:
            self._image_cache = self.generate_image()
        return self._image_cache

    def generate_image(
        self,
        dpi: int = 200,
        rotated: bool = True,
        show_yardages: bool = True,
    ) -> Image.Image:
        """Generate a high-resolution 2D yardage book image of the golf hole.

        If rotated=True, the hole is oriented with the tee at the bottom and
        the green at the top.
        """
        # Determine orientation rotation angle
        rotation_angle = 0.0
        origin = (0.0, 0.0)

        # Transform all geometries to local yards
        def _to_yd(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
            if geom is None or geom.is_empty:
                return None
            return transform(self._to_yards.transform, geom) if self._to_yards else geom

        tee_yd = _to_yd(self.tee_point)
        pin_yd = _to_yd(self.pin)
        cl_yd = _to_yd(self.centerline)

        if rotated:
            # Compute angle from tee to green
            start_pt = None
            end_pt = None

            if tee_yd and pin_yd:
                start_pt, end_pt = tee_yd, pin_yd
            elif cl_yd and len(cl_yd.coords) >= 2:
                start_pt = Point(cl_yd.coords[0])
                end_pt = Point(cl_yd.coords[-1])

            if start_pt and end_pt:
                dx = end_pt.x - start_pt.x
                dy = end_pt.y - start_pt.y
                bearing_deg = math.degrees(math.atan2(dy, dx))
                # Rotate bearing to point straight UP (+Y, 90 degrees)
                rotation_angle = 90.0 - bearing_deg
                origin = ((start_pt.x + end_pt.x) / 2.0, (start_pt.y + end_pt.y) / 2.0)

        def _rot_geom(g_yd: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
            if g_yd is None or g_yd.is_empty:
                return None
            if rotated and abs(rotation_angle) > 1e-3:
                return rotate(g_yd, rotation_angle, origin=origin)
            return g_yd

        def _prep_geom(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
            return _rot_geom(_to_yd(geom))

        # Build playing corridor turf + soft buffer (25 yds) for water hazard clipping
        corridor_elements = []
        if cl_yd and not cl_yd.is_empty:
            corridor_elements.append(cl_yd)
        for fw in self.fairways:
            g = _to_yd(fw.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)
        if self.green:
            g = _to_yd(self.green.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)
        for t in self.tee_boxes:
            g = _to_yd(t.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)

        water_clip = None
        if corridor_elements:
            base_union = unary_union(corridor_elements)
            turf_poly = base_union.buffer(85.0, join_style=1)
            for r in self.rough:
                rg = _to_yd(r.geometry)
                if rg and not rg.is_empty:
                    turf_poly = unary_union([turf_poly, rg])
            water_clip = turf_poly.buffer(25.0, join_style=1)

        # Collect and rotate elements
        r_roughs = [_prep_geom(r.geometry) for r in self.rough]
        r_fairways = [_prep_geom(f.geometry) for f in self.fairways]
        r_tees = [_prep_geom(t.geometry) for t in self.tee_boxes]
        r_bunkers = [_prep_geom(b.geometry) for b in self.bunkers]

        r_waters = []
        for w in self.water_hazards:
            wg = _to_yd(w.geometry)
            if wg and not wg.is_empty:
                if water_clip:
                    clipped = _extract_polygons(wg.intersection(water_clip))
                else:
                    clipped = wg
                if clipped and not clipped.is_empty:
                    rot_w = _rot_geom(clipped)
                    if rot_w and not rot_w.is_empty:
                        r_waters.append(rot_w)

        r_green = _prep_geom(self.green.geometry) if self.green else None
        r_cl = _prep_geom(self.centerline)
        r_pin = _prep_geom(self.pin)
        r_tee = _prep_geom(self.tee_point)

        # Setup figure
        fig, ax = plt.subplots(figsize=(7, 10), facecolor="#1a251b")
        ax.set_facecolor("#1e2e20")  # Dark forest background

        # Helper to plot polygons
        def _plot_poly(geom: Optional[BaseGeometry], facecolor: str, edgecolor: str, alpha: float = 1.0, zorder: int = 1, lw: float = 1.0):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Polygon):
                geoms = [geom]
            elif isinstance(geom, MultiPolygon):
                geoms = list(geom.geoms)
            else:
                return

            for p in geoms:
                x, y = p.exterior.xy
                ax.fill(x, y, facecolor=facecolor, edgecolor=edgecolor, alpha=alpha, zorder=zorder, linewidth=lw)
                for interior in p.interiors:
                    ix, iy = interior.xy
                    ax.fill(ix, iy, facecolor="#1e2e20", edgecolor=edgecolor, alpha=alpha, zorder=zorder + 0.1, linewidth=lw)

        # 1. Plot Rough (Dark Grass)
        for g in r_roughs:
            _plot_poly(g, facecolor="#2d5229", edgecolor="#355e3b", alpha=0.9, zorder=2, lw=0.5)

        # 2. Plot Fairways (Bright Golf Grass)
        for g in r_fairways:
            _plot_poly(g, facecolor="#5b9a42", edgecolor="#4e8838", alpha=0.95, zorder=3, lw=1.0)

        # 3. Plot Tee Boxes
        for g in r_tees:
            _plot_poly(g, facecolor="#3e7732", edgecolor="#ffffff", alpha=0.95, zorder=4, lw=1.2)

        # 4. Plot Green (Lush Emerald)
        if r_green:
            _plot_poly(r_green, facecolor="#27ae60", edgecolor="#2ecc71", alpha=1.0, zorder=5, lw=1.5)

        # 5. Plot Water Hazards (Rich Blue)
        for g in r_waters:
            _plot_poly(g, facecolor="#2980b9", edgecolor="#85c1e9", alpha=0.95, zorder=6, lw=1.2)

        # 6. Plot Bunkers (Sand Khaki)
        for g in r_bunkers:
            _plot_poly(g, facecolor="#edd69a", edgecolor="#bfa15f", alpha=1.0, zorder=7, lw=1.2)

        # 7. Centerline / Line of play
        if r_cl and isinstance(r_cl, LineString):
            cx, cy = r_cl.xy
            ax.plot(cx, cy, color="#ffffff", linestyle="--", linewidth=1.2, alpha=0.45, zorder=8)
        elif r_cl and hasattr(r_cl, "geoms"):
            for line in r_cl.geoms:
                if isinstance(line, LineString):
                    cx, cy = line.xy
                    ax.plot(cx, cy, color="#ffffff", linestyle="--", linewidth=1.2, alpha=0.45, zorder=8)

        # 8. Yardage Markers / Arcs from Pin
        if show_yardages and r_pin and isinstance(r_pin, Point):
            pin_x, pin_y = r_pin.x, r_pin.y
            for arc_yd in [100, 150, 200, 250]:
                if arc_yd < self.length_yards:
                    circle = mpatches.Arc(
                        (pin_x, pin_y),
                        width=arc_yd * 2,
                        height=arc_yd * 2,
                        angle=0,
                        theta1=200,
                        theta2=340,
                        color="#ffffff",
                        linestyle=":",
                        linewidth=0.9,
                        alpha=0.4,
                        zorder=9,
                    )
                    ax.add_patch(circle)
                    # Label the yardage arc
                    ax.text(
                        pin_x,
                        pin_y - arc_yd,
                        f"{arc_yd}",
                        color="#ecf0f1",
                        fontsize=7,
                        fontweight="bold",
                        ha="center",
                        va="center",
                        alpha=0.6,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="#1a251b", edgecolor="none", alpha=0.6),
                        zorder=10,
                    )

        # 9. Pin Flag Marker
        if r_pin and isinstance(r_pin, Point):
            px, py = r_pin.x, r_pin.y
            ax.plot([px, px], [py, py + 8], color="#e74c3c", linewidth=2.0, zorder=12)
            flag = mpatches.Polygon(
                [[px, py + 8], [px + 6, py + 5], [px, py + 2]],
                closed=True,
                facecolor="#e74c3c",
                edgecolor="#c0392b",
                zorder=13,
            )
            ax.add_patch(flag)
            ax.scatter([px], [py], s=35, color="#ffffff", edgecolors="#c0392b", linewidth=1.5, zorder=14)

        # 10. Tee Marker
        if r_tee and isinstance(r_tee, Point):
            ax.scatter([r_tee.x], [r_tee.y], s=50, marker="s", color="#3498db", edgecolors="#ffffff", linewidth=1.5, zorder=12)

        # Auto-compute viewport limits with margin
        all_geoms = [g for g in [r_green, r_cl, r_pin, r_tee] + r_fairways + r_bunkers + r_waters + r_tees if g is not None]
        if all_geoms:
            u = unary_union(all_geoms)
            minx, miny, maxx, maxy = u.bounds
            pad_x = max(25.0, (maxx - minx) * 0.25)
            pad_y = max(30.0, (maxy - miny) * 0.12)
            ax.set_xlim(minx - pad_x, maxx + pad_x)
            ax.set_ylim(miny - pad_y, maxy + pad_y)

        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#34495e")
            spine.set_linewidth(1.0)

        # Title Card Header
        hcp_str = f" • HCP {self.handicap}" if self.handicap else ""
        header_text = f"HOLE {self.hole_number}  |  {self.name.upper()}\nPAR {self.par} • {int(self.length_yards)} YDS{hcp_str}"
        ax.set_title(
            header_text,
            color="#ecf0f1",
            fontsize=12,
            fontweight="bold",
            pad=15,
            linespacing=1.4,
        )

        # Bottom Course Subtitle
        fig.text(
            0.5,
            0.02,
            f"{self.course_name.upper()} • HOLE MAP",
            color="#95a5a6",
            fontsize=8,
            ha="center",
            va="bottom",
            fontweight="semibold",
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        img = Image.open(buf)
        img.load()
        return img

    def save_image(
        self,
        filepath: Union[str, Path],
        dpi: int = 200,
        rotated: bool = True,
        show_yardages: bool = True,
    ) -> Path:
        """Generate and save the hole image to disk."""
        out_path = Path(filepath)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img = self.generate_image(dpi=dpi, rotated=rotated, show_yardages=show_yardages)
        img.save(out_path)
        return out_path

    def __repr__(self) -> str:
        return (
            f"<GolfHole #{self.hole_number}: '{self.name}', Par {self.par}, "
            f"{self.length_yards} yds, {len(self.bunkers)} bunkers, {len(self.water_hazards)} water>"
        )


# ==============================================================================
# Golf Course Container & Ingest Parser
# ==============================================================================

class GolfCourse:
    """Represents a golf course composed of 18 GolfHole objects and course-wide features."""

    def __init__(
        self,
        name: str,
        holes: Optional[dict[int, GolfHole]] = None,
        rough_features: Optional[list[Rough]] = None,
        unassigned_features: Optional[list[GolfFeature]] = None,
    ) -> None:
        self.name = name
        self.holes: dict[int, GolfHole] = holes or {}
        self.rough_features = rough_features or []
        self.unassigned_features = unassigned_features or []

    def get_hole(self, number: int) -> GolfHole:
        """Get GolfHole by hole number (1-18)."""
        if number not in self.holes:
            raise KeyError(f"Hole {number} not found in course '{self.name}'. Available: {sorted(self.holes.keys())}")
        return self.holes[number]

    def export_all_images(
        self,
        output_dir: Union[str, Path],
        dpi: int = 200,
        rotated: bool = True,
    ) -> list[Path]:
        """Export yardage book maps for all holes to a directory."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for num in sorted(self.holes.keys()):
            hole = self.holes[num]
            file_name = f"hole_{num:02d}.png"
            p = hole.save_image(out_dir / file_name, dpi=dpi, rotated=rotated)
            paths.append(p)
        return paths

    def export_interactive_html(
        self,
        output_filepath: Union[str, Path],
        title: Optional[str] = None,
    ) -> Path:
        """Export a self-contained interactive vector HTML5 map viewer for this course."""
        from src.interactive_viewer import export_interactive_html as _export_html
        return _export_html(self, output_filepath, title=title)

    @classmethod
    def from_geojson(
        cls,
        geojson_source: Union[str, Path, dict[str, Any]],
        rough_corridor_yards: float = 75.0,
        target_course_name: Optional[str] = None,
        max_feature_distance_yards: float = 350.0,
    ) -> GolfCourse:
        """Parse a GeoJSON file or dictionary into a GolfCourse object.

        Args:
            geojson_source: File path or parsed GeoJSON dictionary.
            rough_corridor_yards: Yard width to buffer around hole features when clipping course-wide rough.
            target_course_name: Optional name filter if GeoJSON contains multiple courses.
            max_feature_distance_yards: Maximum allowed distance in yards from hole centerline
                before a feature tagged with the same ref is flagged as an outlier (e.g. from an adjacent course).
        """
        if isinstance(geojson_source, (str, Path)):
            with open(geojson_source, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = geojson_source

        features = data.get("features", [])

        # Course name detection
        course_name = target_course_name or "Golf Course"
        if not target_course_name:
            for f in features:
                props = f.get("properties", {})
                cn = props.get("golf:course:name") or props.get("course:name")
                if cn:
                    course_name = cn
                    break

        # Group features by hole ref
        by_hole: dict[int, list[dict[str, Any]]] = {}
        rough_geo_list: list[BaseGeometry] = []
        unassigned: list[GolfFeature] = []

        for f in features:
            props = f.get("properties", {})
            geom_data = f.get("geometry")
            if not geom_data:
                continue

            # Course name filter if explicitly specified
            f_course = props.get("golf:course:name") or props.get("course:name")
            if target_course_name and f_course and f_course.strip().lower() != target_course_name.strip().lower():
                continue

            geom = shape(geom_data)
            golf_type = props.get("golf")

            if golf_type == "rough":
                rough_geo_list.append(geom)
                continue

            hole_num: Optional[int] = None
            raw_ref = props.get("ref") or props.get("hole")
            if raw_ref is not None:
                import re
                match = re.search(r"\b(\d+)\b", str(raw_ref))
                if match:
                    hole_num = int(match.group(1))

            if hole_num is not None:
                by_hole.setdefault(hole_num, []).append(f)
            else:
                unassigned.append(GolfFeature(
                    id=str(props.get("@id", f"feature_{len(unassigned)}")),
                    geometry=geom,
                    name=props.get("name"),
                    description=props.get("description"),
                    surface=props.get("surface"),
                    properties=props,
                ))

        # Union course-wide rough
        course_rough_union: Optional[BaseGeometry] = None
        if rough_geo_list:
            course_rough_union = unary_union(rough_geo_list)

        # Disambiguate multi-course centerlines using spatial routing continuity (e.g. Pebble Beach vs Spyglass vs The Hay)
        has_multi_cl = any(
            len([f for f in by_hole.get(num, []) if f.get("properties", {}).get("golf") == "hole"]) > 1
            for num in range(1, 19)
        )
        if has_multi_cl:
            # 1. Determine anchor point (from GeoJSON properties or first championship centerline)
            anchor: Optional[Point] = None
            if isinstance(data, dict) and data.get("properties", {}).get("bbox"):
                raw_b = data["properties"]["bbox"]
                if len(raw_b) == 4:
                    anchor = Point((raw_b[1] + raw_b[3]) / 2.0, (raw_b[0] + raw_b[2]) / 2.0)

            # Pick anchor Hole 1 (championship length >= 280 yds, closest to anchor or course center)
            h1_feats = [f for f in by_hole.get(1, []) if f.get("properties", {}).get("golf") == "hole"]
            if h1_feats:
                def _score_h1(hf: dict[str, Any]) -> float:
                    g = shape(hf["geometry"])
                    c_pt = g.centroid
                    to_yd_h1, _, _ = _build_yards_transformer(c_pt.x, c_pt.y)
                    g_yd = transform(to_yd_h1.transform, g) if to_yd_h1 else g
                    l_yd = g_yd.length
                    # Penalize short par 3 holes (< 250 yds) on hole 1
                    len_penalty = 10000.0 if l_yd < 250.0 else 0.0
                    if anchor:
                        to_yd_anc, _, _ = _build_yards_transformer(anchor.x, anchor.y)
                        d_anc = float(transform(to_yd_anc.transform, c_pt).distance(transform(to_yd_anc.transform, anchor)))
                    else:
                        d_anc = 0.0
                    return len_penalty + d_anc

                h1_feats.sort(key=_score_h1)
                best_h1 = h1_feats[0]
                by_hole[1] = [f for f in by_hole[1] if f.get("properties", {}).get("golf") != "hole" or f is best_h1]

                # Walk holes 2..18 using green-to-tee routing distance
                prev_cl = shape(best_h1["geometry"])
                for num in range(2, 19):
                    num_feats = [f for f in by_hole.get(num, []) if f.get("properties", {}).get("golf") == "hole"]
                    if len(num_feats) <= 1:
                        if num_feats:
                            prev_cl = shape(num_feats[0]["geometry"])
                        continue

                    prev_green = Point(prev_cl.coords[-1]) if isinstance(prev_cl, LineString) else prev_cl.centroid
                    to_yd_step, _, _ = _build_yards_transformer(prev_green.x, prev_green.y)

                    def _score_step(hf: dict[str, Any]) -> float:
                        g = shape(hf["geometry"])
                        g_yd = transform(to_yd_step.transform, g) if to_yd_step else g
                        l_yd = g_yd.length
                        # Penalize executive pitch-and-putt holes under 90 yds
                        penalty = 5000.0 if l_yd < 90.0 else 0.0
                        tee_pt = Point(g.coords[0]) if isinstance(g, LineString) else g.centroid
                        d_walk = float(transform(to_yd_step.transform, tee_pt).distance(transform(to_yd_step.transform, prev_green))) if to_yd_step else 0.0
                        return penalty + d_walk

                    num_feats.sort(key=_score_step)
                    best_step = num_feats[0]
                    prev_cl = shape(best_step["geometry"])
                    by_hole[num] = [f for f in by_hole[num] if f.get("properties", {}).get("golf") != "hole" or f is best_step]


        # Build each GolfHole
        holes_dict: dict[int, GolfHole] = {}


        for num in sorted(by_hole.keys()):
            hole_feats = by_hole[num]

            # Pick best centerline for this hole (prioritize target course name, named holes, and metadata)
            cl_candidates = [hf for hf in hole_feats if hf.get("properties", {}).get("golf") == "hole"]
            centerline: Optional[LineString] = None
            best_cl_feat: Optional[dict[str, Any]] = None

            if cl_candidates:
                def _score_cl(hf: dict[str, Any]) -> tuple[int, int]:
                    p = hf.get("properties", {})
                    cn = p.get("golf:course:name") or p.get("course:name") or ""
                    matches_course = 1 if (course_name and course_name.lower() in cn.lower()) else 0
                    has_meta = 1 if (p.get("description") or p.get("par")) else 0
                    return (matches_course, has_meta)


                cl_candidates.sort(key=_score_cl, reverse=True)
                best_cl_feat = cl_candidates[0]
                g_best = shape(best_cl_feat["geometry"])
                if isinstance(g_best, LineString):
                    centerline = g_best

                # Remove non-matching duplicate centerline ways from other courses
                if len(cl_candidates) > 1:
                    keep_id = str(best_cl_feat.get("properties", {}).get("@id") or best_cl_feat.get("id"))
                    hole_feats = [
                        hf for hf in hole_feats
                        if hf.get("properties", {}).get("golf") != "hole"
                        or str(hf.get("properties", {}).get("@id") or hf.get("id")) == keep_id
                    ]

            # Spatial outlier protection: reject features far from the hole centerline
            # (e.g., from an adjacent golf course that happens to share the same hole ref)
            if centerline is not None and max_feature_distance_yards is not None:
                c_pt = centerline.centroid
                to_yd_filt, _, _ = _build_yards_transformer(c_pt.x, c_pt.y)
                cl_yd = transform(to_yd_filt.transform, centerline) if to_yd_filt else centerline
                filtered_feats: list[dict[str, Any]] = []
                for hf in hole_feats:
                    p = hf.get("properties", {})
                    if p.get("golf") == "hole":
                        filtered_feats.append(hf)
                        continue
                    g = shape(hf["geometry"])
                    g_yd = transform(to_yd_filt.transform, g) if to_yd_filt else g
                    dist_yd = float(cl_yd.distance(g_yd))
                    if dist_yd <= max_feature_distance_yards:
                        filtered_feats.append(hf)
                    else:
                        unassigned.append(GolfFeature(
                            id=str(p.get("@id", f"feature_{len(unassigned)}")),
                            geometry=g,
                            name=p.get("name"),
                            description=p.get("description"),
                            surface=p.get("surface"),
                            properties=p,
                        ))
                hole_feats = filtered_feats

            pin_pt: Optional[Point] = None
            green_obj: Optional[Green] = None
            tees: list[TeeBox] = []
            fairways: list[Fairway] = []
            bunkers: list[Bunker] = []
            waters: list[WaterHazard] = []

            hole_name = f"Hole {num}"
            par = 4
            handicap = None
            desc = None

            for hf in hole_feats:
                p = hf.get("properties", {})
                g = shape(hf["geometry"])
                g_type = p.get("golf")
                feat_id = str(p.get("@id", ""))

                if g_type == "hole":
                    if isinstance(g, LineString):
                        centerline = g
                    hole_name = p.get("name") or hole_name
                    par = int(p.get("par", par))
                    handicap = p.get("handicap", handicap)
                    desc = p.get("description", desc)

                elif g_type == "pin":
                    if isinstance(g, Point):
                        pin_pt = g

                elif g_type == "green":
                    green_obj = Green(
                        id=feat_id,
                        geometry=g,
                        name=p.get("name"),
                        description=p.get("description"),
                        surface=p.get("surface", "grass"),
                        hole_ref=num,
                        properties=p,
                    )

                elif g_type == "tee":
                    tees.append(TeeBox(
                        id=feat_id,
                        geometry=g,
                        name=p.get("name"),
                        description=p.get("description"),
                        tee_type=p.get("tee", "standard"),
                        surface=p.get("surface", "grass"),
                        hole_ref=num,
                        properties=p,
                    ))

                elif g_type == "fairway":
                    fairways.append(Fairway(
                        id=feat_id,
                        geometry=g,
                        name=p.get("name"),
                        description=p.get("description"),
                        surface=p.get("surface", "grass"),
                        hole_ref=num,
                        properties=p,
                    ))

                elif g_type == "bunker" or p.get("natural") == "sand":
                    b_desc = (p.get("description") or "").lower()
                    b_bunker = (p.get("bunker") or "").lower()
                    b_name = (p.get("name") or "").lower()
                    combined_text = f"{b_desc} {b_bunker} {b_name}"
                    b_type = "greenside" if "greenside" in combined_text else ("fairway" if "fairway" in combined_text else "general")
                    bunkers.append(Bunker(
                        id=feat_id,
                        geometry=g,
                        name=p.get("name"),
                        description=p.get("description"),
                        bunker_type=b_type,
                        natural="sand",
                        hole_ref=num,
                        properties=p,
                    ))

                elif (
                    g_type in ("lateral_water_hazard", "water_hazard")
                    or p.get("natural") == "water"
                    or p.get("waterway") in ("stream", "river", "canal", "drain")
                ):
                    waters.append(WaterHazard(
                        id=feat_id,
                        geometry=g,
                        name=p.get("name"),
                        description=p.get("description"),
                        hazard_type=g_type or "water_hazard",
                        natural="water",
                        hole_ref=num,
                        properties=p,
                    ))

            # Spatial recovery for unassigned features (e.g. green or water crossing centerline without explicit ref)
            if centerline is not None and len(centerline.coords) >= 2:
                pin_candidate = Point(centerline.coords[-1])
                c_ref = centerline.centroid
                to_yd_rec, _, _ = _build_yards_transformer(c_ref.x, c_ref.y)
                cl_rec_yd = transform(to_yd_rec.transform, centerline) if to_yd_rec else centerline

                recovered_unassigned: list[int] = []
                for idx, uf in enumerate(unassigned):
                    u_prop = uf.properties
                    u_golf = u_prop.get("golf")
                    u_nat = u_prop.get("natural")
                    u_geom_yd = transform(to_yd_rec.transform, uf.geometry) if to_yd_rec else uf.geometry

                    # 1. Recover green near centerline terminus if hole has no green
                    if green_obj is None and (u_golf == "green" or u_prop.get("leisure") == "pitch"):
                        dist_to_end = float(u_geom_yd.distance(transform(to_yd_rec.transform, pin_candidate) if to_yd_rec else pin_candidate))
                        if dist_to_end <= 35.0:
                            green_obj = Green(
                                id=uf.id,
                                geometry=uf.geometry,
                                name=uf.name,
                                description=uf.description,
                                surface=uf.surface or "grass",
                                hole_ref=num,
                                properties=u_prop,
                            )
                            recovered_unassigned.append(idx)
                            continue

                    # 2. Recover water hazard if it intersects or is within 10 yards of centerline
                    if (
                        u_golf in ("lateral_water_hazard", "water_hazard")
                        or u_nat == "water"
                        or u_prop.get("waterway") in ("stream", "river", "canal", "drain")
                    ):
                        if cl_rec_yd.intersects(u_geom_yd) or cl_rec_yd.distance(u_geom_yd) <= 10.0:
                            waters.append(WaterHazard(
                                id=uf.id,
                                geometry=uf.geometry,
                                name=uf.name,
                                description=uf.description,
                                hazard_type=u_golf or "water_hazard",
                                natural="water",
                                hole_ref=num,
                                properties=u_prop,
                            ))
                            recovered_unassigned.append(idx)
                            continue

                    # 3. Recover unassigned bunker if within 45 yards of hole centerline or green
                    if u_golf == "bunker" or u_nat == "sand":
                        dist_to_cl = float(cl_rec_yd.distance(u_geom_yd))
                        if dist_to_cl <= 45.0:
                            b_type = "greenside" if (green_obj and float(u_geom_yd.distance(transform(to_yd_rec.transform, green_obj.geometry) if to_yd_rec else green_obj.geometry)) <= 30.0) else "fairway"
                            bunkers.append(Bunker(
                                id=uf.id,
                                geometry=uf.geometry,
                                name=uf.name,
                                description=uf.description,
                                bunker_type=b_type,
                                natural="sand",
                                hole_ref=num,
                                properties=u_prop,
                            ))
                            recovered_unassigned.append(idx)
                            continue


                # Remove recovered features from unassigned list (in reverse index order)
                for r_idx in sorted(set(recovered_unassigned), reverse=True):
                    unassigned.pop(r_idx)

            # Assign bunker type geometrically if still 'general' and green exists
            if green_obj:
                c_green = green_obj.geometry.centroid
                is_geographic = not (abs(c_green.y) > 90.0 or abs(c_green.x) > 180.0)
                for b in bunkers:
                    if b.bunker_type == "general":
                        # If bunker is within ~45 yards of green, call it greenside
                        dist_val = b.geometry.distance(green_obj.geometry)
                        threshold = 0.00045 if is_geographic else 45.0
                        if dist_val < threshold:
                            b.bunker_type = "greenside"
                        else:
                            b.bunker_type = "fairway"

            # Rough Corridor Extraction
            hole_rough_list: list[Rough] = []
            if course_rough_union is not None:
                # Create corridor from centerline or fairways
                corridor_base_list = []
                if centerline:
                    corridor_base_list.append(centerline)
                corridor_base_list.extend([f.geometry for f in fairways])
                if green_obj:
                    corridor_base_list.append(green_obj.geometry)
                corridor_base_list.extend([t.geometry for t in tees])

                if corridor_base_list:
                    hole_base = unary_union(corridor_base_list)
                    # Use local yard projection for accurate yard corridor buffer
                    ref_c = hole_base.centroid
                    to_yd, to_wgs_rev, _ = _build_yards_transformer(ref_c.x, ref_c.y)

                    hole_base_yd = transform(to_yd.transform, hole_base)
                    corridor_yd = hole_base_yd.buffer(rough_corridor_yards)
                    course_rough_yd = transform(to_yd.transform, course_rough_union)

                    clipped_rough_yd = course_rough_yd.intersection(corridor_yd)
                    if not clipped_rough_yd.is_empty:
                        clipped_rough_wgs = transform(to_wgs_rev.transform, clipped_rough_yd)
                        hole_rough_list.append(Rough(
                            id=f"rough_hole_{num}",
                            geometry=clipped_rough_wgs,
                            name=f"Hole {num} Rough",
                            hole_ref=num,
                        ))

            holes_dict[num] = GolfHole(
                hole_number=num,
                name=hole_name,
                par=par,
                handicap=handicap,
                course_name=course_name,
                description=desc,
                centerline=centerline,
                pin=pin_pt,
                tee_boxes=tees,
                fairways=fairways,
                green=green_obj,
                bunkers=bunkers,
                water_hazards=waters,
                rough=hole_rough_list,
            )

        # Spatial recovery for unassigned fairways (e.g. courses where OSM has no ref tags on fairways)
        unassigned_fairways = [(idx, uf) for idx, uf in enumerate(unassigned) if uf.properties.get("golf") == "fairway"]
        if unassigned_fairways:
            fairway_assignments: dict[int, tuple[int, float]] = {}  # uf_idx -> (hole_num, dist_centroid)
            for h_num, hole in holes_dict.items():
                if not hole.centerline:
                    continue
                to_yd = hole._to_yards
                cl_yd = transform(to_yd.transform, hole.centerline) if to_yd else hole.centerline

                for uf_idx, uf in unassigned_fairways:
                    g_yd = transform(to_yd.transform, uf.geometry) if to_yd else uf.geometry
                    dist = float(cl_yd.distance(g_yd))
                    if dist <= 40.0:
                        dist_c = float(cl_yd.distance(g_yd.centroid))
                        if uf_idx not in fairway_assignments or dist_c < fairway_assignments[uf_idx][1]:
                            fairway_assignments[uf_idx] = (h_num, dist_c)

            recovered_fw_indices = set()
            for uf_idx, (h_num, _) in fairway_assignments.items():
                uf = unassigned[uf_idx]
                holes_dict[h_num].fairways.append(Fairway(
                    id=uf.id,
                    geometry=uf.geometry,
                    name=uf.name,
                    description=uf.description,
                    surface=uf.surface or "grass",
                    hole_ref=h_num,
                    properties=uf.properties,
                ))
                recovered_fw_indices.add(uf_idx)

            for r_idx in sorted(recovered_fw_indices, reverse=True):
                unassigned.pop(r_idx)

        # Resolve greens for any holes that gained recovered fairways or have synthetic greens
        for hole in holes_dict.values():
            if hole.green is None or hole.green.properties.get("synthetic"):
                hole._resolve_green()


        course_roughs = [
            Rough(id=f"course_rough_{i}", geometry=rg, name="Course Rough")
            for i, rg in enumerate(rough_geo_list)
        ]

        return cls(
            name=course_name,
            holes=holes_dict,
            rough_features=course_roughs,
            unassigned_features=unassigned,
        )

    def __repr__(self) -> str:
        return f"<GolfCourse: '{self.name}', {len(self.holes)} holes>"


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse golf course GeoJSON and generate hole maps/models.")
    parser.add_argument("geojson", type=Path, help="Path to golf course GeoJSON file")
    parser.add_argument("--course-name", type=str, default=None, help="Specific course name to filter if multi-course")
    parser.add_argument("--export-images", type=Path, default=None, help="Directory to export hole images")
    parser.add_argument("--export-html", type=Path, default=None, help="Path to export standalone interactive HTML map viewer")
    parser.add_argument("--hole", type=int, default=None, help="Specific hole number to inspect")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for exported images")
    args = parser.parse_args()

    print(f"Loading course from {args.geojson}...")
    course = GolfCourse.from_geojson(args.geojson, target_course_name=args.course_name)
    print(f"Loaded: {course}")

    if args.hole:
        hole = course.get_hole(args.hole)
        print(f"\n{hole}")
        print(f"  Par: {hole.par}, Length: {hole.length_yards} yards, HCP: {hole.handicap}")
        print(f"  Tee boxes: {len(hole.tee_boxes)}")
        print(f"  Fairways: {len(hole.fairways)}")
        print(f"  Bunkers: {len(hole.bunkers)}")
        for b in hole.bunkers:
            print(f"    - Bunker: type={b.bunker_type}, desc={b.description}")
        print(f"  Water hazards: {len(hole.water_hazards)}")
        print(f"  Pin location: {hole.pin}")
        if args.export_images:
            out_img = args.export_images / f"hole_{hole.hole_number:02d}.png"
            hole.save_image(out_img, dpi=args.dpi)
            print(f"  Saved image: {out_img}")
    else:
        for num in sorted(course.holes.keys()):
            h = course.holes[num]
            print(f"  Hole {num:2d} | {h.name:20s} | Par {h.par} | {int(h.length_yards):3d} yds | Bunkers: {len(h.bunkers)} | Water: {len(h.water_hazards)}")

        if args.export_images:
            print(f"\nExporting all hole maps to {args.export_images}...")
            paths = course.export_all_images(args.export_images, dpi=args.dpi)
            print(f"Exported {len(paths)} hole images.")

    if args.export_html:
        html_path = course.export_interactive_html(args.export_html)
        print(f"Exported interactive map viewer to: {html_path}")


if __name__ == "__main__":
    main()
