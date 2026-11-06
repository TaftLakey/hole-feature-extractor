"""Interactive Golf Course HTML5 Vector Viewer Generator.

Generates a standalone, zero-dependency HTML/JS file with vector rendering,
smooth auto-rotation (Hole-Up), hole-by-hole navigation, interactive
point-and-click multi-shot planning, hazard carry tooltips, and a true spatial
overview map with full rough/turf gap-filling, tee spots, property window framing,
pan-versus-target mode selection, and hole confirmation popups.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import pyproj
from shapely.affinity import rotate
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import transform, unary_union

if TYPE_CHECKING:
    from src.course_geometry import GolfCourse, GolfHole


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


def _geom_to_svg_path(geom: Any) -> str:
    """Convert a Shapely polygon/multipolygon to an SVG path string with inverted Y (North=Up)."""
    if geom is None or geom.is_empty:
        return ""

    paths = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)
    else:
        return ""

    for p in polys:
        ext = p.exterior.coords
        if len(ext) < 3:
            continue
        p_str = f"M {ext[0][0]:.2f} {-ext[0][1]:.2f} " + " ".join(f"L {x:.2f} {-y:.2f}" for x, y in ext[1:]) + " Z"
        for interior in p.interiors:
            i_coords = interior.coords
            if len(i_coords) >= 3:
                p_str += f" M {i_coords[0][0]:.2f} {-i_coords[0][1]:.2f} " + " ".join(f"L {x:.2f} {-y:.2f}" for x, y in i_coords[1:]) + " Z"
        paths.append(p_str)

    return " ".join(paths)


def _line_to_svg_path(geom: Any) -> str:
    """Convert a Shapely LineString to an SVG path string with inverted Y (North=Up)."""
    if geom is None or geom.is_empty:
        return ""
    if isinstance(geom, LineString) and len(geom.coords) >= 2:
        return f"M {geom.coords[0][0]:.2f} {-geom.coords[0][1]:.2f} " + " ".join(f"L {x:.2f} {-y:.2f}" for x, y in geom.coords[1:])
    return ""


def serialize_course_data(course: GolfCourse, turf_buffer_yards: float = 85.0) -> dict[str, Any]:
    """Serialize a GolfCourse into a normalized, self-contained JSON data contract.

    Includes both local hole yardage geometries (Hole-Up and North-Up) and a
    unified global course coordinate system with seamless property-wide turf rough.
    """
    # 1. Determine global course center for overall course projection
    all_hole_coords = []
    for h in course.holes.values():
        if h.centerline:
            all_hole_coords.extend(h.centerline.coords)
        if h.pin:
            all_hole_coords.append((h.pin.x, h.pin.y))
        if h.tee_point:
            all_hole_coords.append((h.tee_point.x, h.tee_point.y))

    if all_hole_coords:
        lons = [c[0] for c in all_hole_coords]
        lats = [c[1] for c in all_hole_coords]
        course_center_lon = sum(lons) / len(lons)
        course_center_lat = sum(lats) / len(lats)
    else:
        course_center_lon, course_center_lat = -82.02, 33.50

    crs_wgs = "EPSG:4326"
    crs_global = f"+proj=tmerc +lat_0={course_center_lat} +lon_0={course_center_lon} +units=us-yd +ellps=WGS84"
    to_global_yd = pyproj.Transformer.from_crs(crs_wgs, crs_global, always_xy=True)

    def _to_global(geom: Any) -> Any:
        if geom is None or geom.is_empty:
            return None
        return transform(to_global_yd.transform, geom)

    holes_data = []
    overview_fairways = []
    overview_greens = []
    overview_tees = []
    overview_bunkers = []
    overview_waters = []
    overview_centerlines = []
    overview_labels = []
    all_course_elements = []
    raw_overview_waters = []
    seen_overview_water_ids: set[str] = set()

    for num in sorted(course.holes.keys()):
        h: GolfHole = course.holes[num]
        to_yd = h._to_yards

        def _yd(geom: Any) -> Any:
            if geom is None or geom.is_empty or to_yd is None:
                return geom
            return transform(to_yd.transform, geom)

        tee_yd = _yd(h.tee_point)
        pin_yd = _yd(h.pin)
        cl_yd = _yd(h.centerline)

        # Calculate rotation angle so tee is at bottom and pin is at top
        rotation_deg = 0.0
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
            # Rotate bearing so it points straight UP (+Y in northing, which becomes -Y in SVG)
            rotation_deg = 90.0 - bearing_deg
            origin = ((start_pt.x + end_pt.x) / 2.0, (start_pt.y + end_pt.y) / 2.0)
        else:
            origin = (0.0, 0.0)

        def _rot(geom: Any) -> Any:
            if geom is None or geom.is_empty:
                return None
            if abs(rotation_deg) > 1e-3:
                return rotate(geom, rotation_deg, origin=origin)
            return geom

        # 1. Smart Hole Turf Buffer (continuous rough around line of play)
        corridor_elements = []
        if cl_yd and not cl_yd.is_empty:
            corridor_elements.append(cl_yd)
        for fw in h.fairways:
            g = _yd(fw.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)
        if h.green:
            g = _yd(h.green.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)
        for t in h.tee_boxes:
            g = _yd(t.geometry)
            if g and not g.is_empty:
                corridor_elements.append(g)

        smart_turf_poly = None
        if corridor_elements:
            base_union = unary_union(corridor_elements)
            buffered = base_union.buffer(turf_buffer_yards, join_style=1)
            for r in h.rough:
                rg = _yd(r.geometry)
                if rg and not rg.is_empty:
                    buffered = unary_union([buffered, rg])
            smart_turf_poly = buffered

        # Soft Boundary (+25 yards past outer turf) for hole-level water clipping
        hole_water_clip = smart_turf_poly.buffer(25.0, join_style=1) if smart_turf_poly else None

        # Local Hole-Up rotated geometries
        r_turf = _rot(smart_turf_poly)
        r_fairways = [_rot(_yd(f.geometry)) for f in h.fairways]
        r_green = _rot(_yd(h.green.geometry)) if h.green else None
        r_tees = [_rot(_yd(t.geometry)) for t in h.tee_boxes]
        r_bunkers = [_rot(_yd(b.geometry)) for b in h.bunkers]
        r_cl = _rot(cl_yd)
        r_pin = _rot(pin_yd)
        r_tee = _rot(tee_yd)

        # Local North-up geometries
        n_turf = smart_turf_poly
        n_fairways = [_yd(f.geometry) for f in h.fairways]
        n_green = _yd(h.green.geometry) if h.green else None
        n_tees = [_yd(t.geometry) for t in h.tee_boxes]
        n_bunkers = [_yd(b.geometry) for b in h.bunkers]
        n_cl = cl_yd
        n_pin = pin_yd
        n_tee = tee_yd

        # Bunkers
        bunkers_data = []
        for b, r_b, n_b in zip(h.bunkers, r_bunkers, n_bunkers):
            if r_b is None or r_b.is_empty:
                continue
            dist_tee = round(h.distance_to_hazard(h.tee_point, b), 1) if h.tee_point else 0.0
            dist_pin = round(h.distance_to_hazard(h.pin, b), 1) if h.pin else 0.0
            bunkers_data.append({
                "id": b.id,
                "name": b.name or "Bunker",
                "type": b.bunker_type,
                "dist_tee": dist_tee,
                "dist_pin": dist_pin,
                "path_hole_up": _geom_to_svg_path(r_b),
                "path_north": _geom_to_svg_path(n_b),
            })

        # Water hazards clipped to hole corridor + soft boundary (25 yds)
        waters_data = []
        r_waters = []
        n_waters = []
        for w in h.water_hazards:
            wg = _yd(w.geometry)
            if wg is None or wg.is_empty:
                continue
            if hole_water_clip:
                clipped = _extract_polygons(wg.intersection(hole_water_clip))
            else:
                clipped = wg
            if clipped is None or clipped.is_empty:
                continue

            r_w = _rot(clipped)
            n_w = clipped
            r_waters.append(r_w)
            n_waters.append(n_w)

            dist_tee = round(h.distance_to_hazard(h.tee_point, w), 1) if h.tee_point else 0.0
            dist_pin = round(h.distance_to_hazard(h.pin, w), 1) if h.pin else 0.0
            waters_data.append({
                "id": w.id,
                "name": w.name or "Water Hazard",
                "dist_tee": dist_tee,
                "dist_pin": dist_pin,
                "path_hole_up": _geom_to_svg_path(r_w),
                "path_north": _geom_to_svg_path(n_w),
            })

        # Hole-Up rotated view bounds in SVG coordinates [x, y, w, h]
        all_geoms_rot = [g for g in [r_turf, r_green, r_cl, r_pin, r_tee] + r_fairways + r_bunkers + r_waters + r_tees if g is not None and not g.is_empty]
        if all_geoms_rot:
            u_rot = unary_union(all_geoms_rot)
            minx, miny, maxx, maxy = u_rot.bounds
            pad_x = max(25.0, (maxx - minx) * 0.20)
            pad_y = max(30.0, (maxy - miny) * 0.15)
            # Invert Y for SVG: svg_min_y is -(maxy + pad_y)
            view_bounds_hole_up = [
                round(minx - pad_x, 1),
                round(-(maxy + pad_y), 1),
                round((maxx - minx) + 2 * pad_x, 1),
                round((maxy - miny) + 2 * pad_y, 1),
            ]
        else:
            view_bounds_hole_up = [-100.0, -450.0, 200.0, 500.0]

        # North-up view bounds in SVG coordinates
        all_geoms_north = [g for g in [n_turf, n_green, n_cl, n_pin, n_tee] + n_fairways + n_bunkers + n_waters + n_tees if g is not None and not g.is_empty]
        if all_geoms_north:
            u_north = unary_union(all_geoms_north)
            minx, miny, maxx, maxy = u_north.bounds
            pad_x = max(25.0, (maxx - minx) * 0.20)
            pad_y = max(30.0, (maxy - miny) * 0.15)
            view_bounds_north = [
                round(minx - pad_x, 1),
                round(-(maxy + pad_y), 1),
                round((maxx - minx) + 2 * pad_x, 1),
                round((maxy - miny) + 2 * pad_y, 1),
            ]
        else:
            view_bounds_north = view_bounds_hole_up

        hole_payload = {
            "number": h.hole_number,
            "name": h.name,
            "par": h.par,
            "handicap": h.handicap,
            "length_yards": int(h.length_yards),
            "rotation_deg": round(rotation_deg, 2),
            "bounds_hole_up": view_bounds_hole_up,
            "bounds_north": view_bounds_north,
            "pin": {
                "hole_up": {"x": round(r_pin.x, 2) if r_pin else 0.0, "y": round(-r_pin.y, 2) if r_pin else 0.0},
                "north": {"x": round(n_pin.x, 2) if n_pin else 0.0, "y": round(-n_pin.y, 2) if n_pin else 0.0},
            },
            "tee": {
                "hole_up": {"x": round(r_tee.x, 2) if r_tee else 0.0, "y": round(-r_tee.y, 2) if r_tee else 0.0},
                "north": {"x": round(n_tee.x, 2) if n_tee else 0.0, "y": round(-n_tee.y, 2) if n_tee else 0.0},
            },
            "paths": {
                "hole_up": {
                    "turf": _geom_to_svg_path(r_turf),
                    "green": _geom_to_svg_path(r_green),
                    "fairways": [_geom_to_svg_path(f) for f in r_fairways if f],
                    "tees": [_geom_to_svg_path(t) for t in r_tees if t],
                    "centerline": _line_to_svg_path(r_cl),
                },
                "north": {
                    "turf": _geom_to_svg_path(n_turf),
                    "green": _geom_to_svg_path(n_green),
                    "fairways": [_geom_to_svg_path(f) for f in n_fairways if f],
                    "tees": [_geom_to_svg_path(t) for t in n_tees if t],
                    "centerline": _line_to_svg_path(n_cl),
                },
            },
            "bunkers": bunkers_data,
            "waters": waters_data,
        }
        holes_data.append(hole_payload)

        # 2. Add to Global Overview Collection in true spatial coordinates
        g_cl = _to_global(h.centerline)
        if g_cl and not g_cl.is_empty:
            overview_centerlines.append({"hole": num, "path": _line_to_svg_path(g_cl)})
            all_course_elements.append(g_cl)

        for fw in h.fairways:
            g_fw = _to_global(fw.geometry)
            if g_fw and not g_fw.is_empty:
                overview_fairways.append({"hole": num, "path": _geom_to_svg_path(g_fw)})
                all_course_elements.append(g_fw)

        if h.green:
            g_gr = _to_global(h.green.geometry)
            if g_gr and not g_gr.is_empty:
                overview_greens.append({"hole": num, "path": _geom_to_svg_path(g_gr)})
                all_course_elements.append(g_gr)

        for t in h.tee_boxes:
            g_t = _to_global(t.geometry)
            if g_t and not g_t.is_empty:
                overview_tees.append({
                    "hole": num,
                    "path": _geom_to_svg_path(g_t),
                    "center": [round(g_t.centroid.x, 1), round(-g_t.centroid.y, 1)],
                })
                all_course_elements.append(g_t)

        for b in h.bunkers:
            g_b = _to_global(b.geometry)
            if g_b and not g_b.is_empty:
                overview_bunkers.append({"hole": num, "name": b.name, "path": _geom_to_svg_path(g_b)})

        for w in h.water_hazards:
            w_id = w.id or f"{num}_{id(w)}"
            if w_id not in seen_overview_water_ids:
                seen_overview_water_ids.add(w_id)
                g_w = _to_global(w.geometry)
                if g_w and not g_w.is_empty:
                    raw_overview_waters.append({"hole": num, "name": w.name, "geom": g_w})

        # Label position (near green or midpoint of fairway)
        g_pin = _to_global(h.pin)
        if g_pin and not g_pin.is_empty:
            lx, ly = g_pin.x, g_pin.y
        elif g_cl and len(g_cl.coords) >= 2:
            lx, ly = g_cl.coords[-1]
        else:
            lx, ly = 0.0, 0.0

        overview_labels.append({
            "hole": num,
            "x": round(lx, 1),
            "y": round(-ly, 1),
            "name": h.name,
            "par": h.par,
            "yards": int(h.length_yards),
            "handicap": h.handicap or "--",
        })

    # Continuous Property-Wide Turf Rough across all 18 holes
    overview_turf_path = ""
    if all_course_elements:
        base_u_course = unary_union(all_course_elements)
        course_turf_poly = base_u_course.buffer(turf_buffer_yards, join_style=1)
        for rg in course.rough_features:
            rg_glob = _to_global(rg.geometry)
            if rg_glob and not rg_glob.is_empty:
                course_turf_poly = unary_union([course_turf_poly, rg_glob])
        overview_turf_path = _geom_to_svg_path(course_turf_poly)

        # Soft Boundary (+25 yards past outer turf) for regional overview water hazards
        water_clip_poly = course_turf_poly.buffer(25.0, join_style=1)
        for item in raw_overview_waters:
            g_w = item["geom"]
            g_w_clipped = _extract_polygons(g_w.intersection(water_clip_poly))
            if g_w_clipped and not g_w_clipped.is_empty:
                overview_waters.append({
                    "hole": item["hole"],
                    "name": item["name"],
                    "path": _geom_to_svg_path(g_w_clipped),
                })

    # Overview Bounding Box in global SVG coordinates [x, y, w, h]
    if all_course_elements:
        u_all = unary_union(all_course_elements)
        minx, miny, maxx, maxy = u_all.bounds
        pad_x = max(80.0, (maxx - minx) * 0.10)
        pad_y = max(80.0, (maxy - miny) * 0.10)
        overview_bounds = [
            round(minx - pad_x, 1),
            round(-(maxy + pad_y), 1),
            round((maxx - minx) + 2 * pad_x, 1),
            round((maxy - miny) + 2 * pad_y, 1),
        ]
    else:
        overview_bounds = [-600.0, -600.0, 1200.0, 1200.0]

    return {
        "course_name": course.name,
        "total_holes": len(holes_data),
        "total_par": sum(h["par"] for h in holes_data),
        "total_yards": sum(h["length_yards"] for h in holes_data),
        "overview": {
            "bounds": overview_bounds,
            "turf_path": overview_turf_path,
            "fairways": overview_fairways,
            "greens": overview_greens,
            "tees": overview_tees,
            "bunkers": overview_bunkers,
            "waters": overview_waters,
            "centerlines": overview_centerlines,
            "labels": overview_labels,
        },
        "holes": holes_data,
    }


def generate_interactive_html(course: GolfCourse, title: Optional[str] = None) -> str:
    """Generate self-contained standalone HTML5 interactive course viewer."""
    course_data = serialize_course_data(course)
    course_name = title or course.name
    data_json = json.dumps(course_data, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{course_name} - Interactive Course Map</title>
<style>
  :root {{
    --bg-dark: #0f1511;
    --bg-property: #152217;
    --bg-card: #18261c;
    --bg-card-hover: #223628;
    --border-color: #2b4231;
    --border-frame: #34543b;
    --accent: #2ecc71;
    --accent-hover: #27ae60;
    --text-primary: #ecf0f1;
    --text-secondary: #95a5a6;
    --fairway: #5b9a42;
    --green-surface: #27ae60;
    --bunker: #edd69a;
    --water: #2980b9;
    --rough: #274724;
    --tee-box: #3e7732;
    --target-gold: #f1c40f;
    --approach-red: #e74c3c;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: var(--bg-dark);
    color: var(--text-primary);
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }}

  /* Top Navigation Bar - Clean, Static Layout */
  header {{
    background: var(--bg-card);
    border-bottom: 1px solid var(--border-color);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    z-index: 20;
    flex-shrink: 0;
  }}

  .header-left {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .course-title {{
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
  }}

  .course-meta {{
    font-size: 12px;
    color: var(--text-secondary);
  }}

  .hole-pills {{
    display: flex;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    padding: 2px 4px;
  }}

  .pill-btn {{
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }}

  .pill-btn:hover {{
    background: var(--bg-card-hover);
    color: var(--text-primary);
    border-color: var(--accent);
  }}

  .pill-btn.active {{
    background: var(--accent);
    color: #111;
    border-color: var(--accent);
  }}

  .header-actions {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }}

  .action-btn {{
    background: var(--bg-card-hover);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;
  }}

  .action-btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}

  main {{
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 16px 20px;
    background: radial-gradient(circle at center, #111a13 0%, #080d09 100%);
  }}

  /* Centered Framed Canvas Stage */
  .course-stage-frame {{
    position: relative;
    width: 100%;
    height: 100%;
    max-width: 1600px;
    border-radius: 14px;
    background: #142017;
    border: 2px solid #2e4533;
    box-shadow: 0 16px 44px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.5);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}

  /* Fixed Stage Plaque Header */
  .stage-plaque-header {{
    background: linear-gradient(180deg, #18281d 0%, #121e16 100%);
    border-bottom: 1px solid #243829;
    padding: 9px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    z-index: 12;
    user-select: none;
  }}

  .stage-plaque-title {{
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: var(--accent);
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .plaque-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
    display: inline-block;
  }}

  .stage-plaque-sub {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: var(--text-secondary);
    text-transform: uppercase;
  }}

  #map-container {{
    flex: 1;
    width: 100%;
    height: 100%;
    position: relative;
    background: radial-gradient(circle at center, #18281b 0%, #0d140e 100%);
    overflow: hidden;
    cursor: grab;
  }}

  #map-container.panning {{
    cursor: grabbing;
  }}

  #map-container.targeting {{
    cursor: crosshair;
  }}

  #map-svg {{
    width: 100%;
    height: 100%;
    display: block;
    user-select: none;
  }}

  /* Top Right In-Window Floating Orientation Button */
  .map-top-right {{
    position: absolute;
    top: 16px;
    right: 16px;
    z-index: 10;
  }}

  .overlay-btn {{
    background: rgba(24, 38, 28, 0.94);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    transition: all 0.15s ease;
  }}

  .overlay-btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}

  /* Top Left Hole Card */
  .floating-card {{
    position: absolute;
    top: 16px;
    left: 16px;
    background: rgba(24, 38, 28, 0.94);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    z-index: 10;
    min-width: 210px;
    pointer-events: none;
  }}

  .hole-header {{
    font-size: 18px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.5px;
  }}

  .hole-sub {{
    font-size: 12px;
    color: var(--text-secondary);
    text-transform: uppercase;
    margin-bottom: 10px;
  }}

  .stat-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding-top: 8px;
  }}

  .stat-item {{
    text-align: center;
  }}

  .stat-val {{
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
  }}

  .stat-label {{
    font-size: 10px;
    color: var(--text-secondary);
    text-transform: uppercase;
  }}

  /* Bottom Left Multi-Shot Planner Menu */
  .shot-planner-card {{
    position: absolute;
    bottom: 20px;
    left: 16px;
    background: rgba(24, 38, 28, 0.96);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6);
    z-index: 15;
    min-width: 280px;
    max-width: 340px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}

  .planner-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 8px;
  }}

  .planner-title-row {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .planner-title {{
    font-size: 12px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }}

  .mode-indicator {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 700;
    text-transform: uppercase;
  }}

  .mode-indicator.explore {{
    background: rgba(149, 165, 166, 0.2);
    color: var(--text-secondary);
  }}

  .mode-indicator.target {{
    background: rgba(241, 196, 15, 0.2);
    color: var(--target-gold);
    border: 1px solid rgba(241, 196, 15, 0.4);
  }}

  .planner-clear-btn {{
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 11px;
    cursor: pointer;
    font-weight: 600;
  }}

  .planner-clear-btn:hover {{
    color: #e74c3c;
  }}

  .shot-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 160px;
    overflow-y: auto;
  }}

  .shot-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    font-size: 12px;
  }}

  .shot-row-name {{
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .shot-badge {{
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--target-gold);
    color: #111;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 800;
  }}

  .shot-row-val {{
    font-weight: 800;
    color: var(--target-gold);
  }}

  .remaining-row {{
    background: rgba(231, 76, 60, 0.12);
    border: 1px dashed rgba(231, 76, 60, 0.4);
    color: var(--approach-red);
  }}

  .remaining-row .shot-row-val {{
    color: var(--approach-red);
  }}

  .planner-actions {{
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }}

  .planner-btn {{
    flex: 1;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    border: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    transition: all 0.15s ease;
  }}

  .planner-btn.primary {{
    background: var(--accent);
    color: #111;
    border-color: var(--accent);
  }}

  .planner-btn.primary:hover {{
    background: var(--accent-hover);
  }}

  .planner-btn.secondary {{
    background: var(--bg-card-hover);
    color: var(--text-primary);
  }}

  .planner-btn.secondary:hover {{
    border-color: var(--accent);
  }}

  /* Overview Hole Selection Popup Card */
  .overview-hole-popup {{
    position: absolute;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(20, 32, 23, 0.98);
    backdrop-filter: blur(10px);
    border: 1px solid var(--accent);
    border-radius: 12px;
    padding: 14px 20px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.7);
    z-index: 25;
    display: none;
    align-items: center;
    gap: 20px;
    animation: popupFadeIn 0.2s ease-out;
  }}

  @keyframes popupFadeIn {{
    from {{ opacity: 0; transform: translate(-50%, 10px); }}
    to {{ opacity: 1; transform: translate(-50%, 0); }}
  }}

  .popup-left {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}

  .popup-title {{
    font-size: 16px;
    font-weight: 800;
    color: var(--accent);
  }}

  .popup-meta {{
    font-size: 12px;
    color: var(--text-secondary);
  }}

  .popup-actions {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}

  .popup-enter-btn {{
    background: var(--accent);
    color: #111;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 800;
    cursor: pointer;
    transition: all 0.15s ease;
  }}

  .popup-enter-btn:hover {{
    background: var(--accent-hover);
    transform: translateY(-1px);
  }}

  .popup-dismiss-btn {{
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 7px 10px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
  }}

  .popup-dismiss-btn:hover {{
    color: var(--text-primary);
  }}

  /* Tooltip */
  #tooltip {{
    position: absolute;
    background: rgba(18, 24, 20, 0.96);
    border: 1px solid var(--accent);
    color: var(--text-primary);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 11px;
    pointer-events: none;
    z-index: 30;
    display: none;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    transform: translate(-50%, -120%);
    white-space: nowrap;
  }}

  /* Map Controls (Zoom) */
  .map-controls {{
    position: absolute;
    bottom: 20px;
    right: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 10;
  }}

  .ctrl-btn {{
    width: 38px;
    height: 38px;
    background: rgba(24, 38, 28, 0.92);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 8px;
    font-size: 18px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }}

  .ctrl-btn:hover {{
    background: var(--bg-card-hover);
    border-color: var(--accent);
    color: var(--accent);
  }}
</style>
</head>
<body>

<header>
  <div class="header-left">
    <div>
      <div class="course-title" id="course-name">{course_name}</div>
      <div class="course-meta">{course_data["total_holes"]} Holes • Par {course_data["total_par"]} • {course_data["total_yards"]} Yards</div>
    </div>
  </div>

  <div class="hole-pills" id="pills-container"></div>

  <div class="header-actions">
    <button class="action-btn" id="btn-prev" title="Previous Hole">◀ Prev</button>
    <button class="action-btn" id="btn-next" title="Next Hole">Next ▶</button>
  </div>
</header>

<main>
  <div class="course-stage-frame">
    <!-- Fixed Plaque Header -->
    <div class="stage-plaque-header">
      <div class="stage-plaque-title">
        <span class="plaque-dot"></span>
        <span id="plaque-title-text">{course_name.upper()} • PROPERTY OVERVIEW</span>
      </div>
      <div class="stage-plaque-sub" id="stage-plaque-sub">{course_data["total_holes"]} HOLES • PAR {course_data["total_par"]} • {course_data["total_yards"]} YARDS</div>
    </div>

    <div id="map-container">
    <!-- In-Window Floating Orientation Button (Top Right) -->
    <div class="map-top-right">
      <button class="overlay-btn" id="btn-toggle-view" title="Toggle Hole-Up / North-Up">🎯 Hole-Up</button>
    </div>

    <svg id="map-svg" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid meet">
      <defs>
        <g id="flag-icon">
          <line x1="0" y1="0" x2="0" y2="-14" stroke="#e74c3c" stroke-width="2.2"/>
          <polygon points="0,-14 9,-9 0,-5" fill="#e74c3c"/>
          <circle cx="0" cy="0" r="3.5" fill="#ffffff" stroke="#c0392b" stroke-width="1.5"/>
        </g>
        <g id="tee-icon">
          <rect x="-4" y="-4" width="8" height="8" fill="#3498db" stroke="#ffffff" stroke-width="1.5"/>
        </g>
      </defs>

      <!-- SVG Layers -->
      <g id="layer-frame"></g>
      <g id="layer-turf"></g>
      <g id="layer-fairways"></g>
      <g id="layer-tees"></g>
      <g id="layer-green"></g>
      <g id="layer-bunkers"></g>
      <g id="layer-water"></g>
      <g id="layer-lines"></g>
      <g id="layer-arcs"></g>
      <g id="layer-markers"></g>
      <g id="layer-shots"></g>
      <g id="layer-overview-labels"></g>
    </svg>

    <!-- Top Left Current Hole Card -->
    <div class="floating-card" id="hole-card">
      <div class="hole-header" id="card-hole-num">HOLE 1</div>
      <div class="hole-sub" id="card-hole-name">TEA OLIVE</div>
      <div class="stat-grid">
        <div class="stat-item">
          <div class="stat-val" id="card-par">4</div>
          <div class="stat-label">Par</div>
        </div>
        <div class="stat-item">
          <div class="stat-val" id="card-yds">447</div>
          <div class="stat-label">Yards</div>
        </div>
        <div class="stat-item">
          <div class="stat-val" id="card-hcp">5</div>
          <div class="stat-label">HCP</div>
        </div>
      </div>
    </div>

    <!-- Bottom Left Multi-Shot Planner Menu -->
    <div class="shot-planner-card" id="shot-planner-card">
      <div class="planner-header">
        <div class="planner-title-row">
          <span class="planner-title">Shot Planner</span>
          <span class="mode-indicator explore" id="mode-badge">🖐️ Pan</span>
        </div>
        <button class="planner-clear-btn" id="btn-clear-shots">Clear All</button>
      </div>
      <div class="shot-list" id="shot-list"></div>
      <div class="planner-actions">
        <button class="planner-btn primary" id="btn-place-shot">🎯 Place Shot</button>
        <button class="planner-btn secondary" id="btn-toggle-pan">🖐️ Pan Mode</button>
        <button class="planner-btn secondary" id="btn-undo-shot">Undo</button>
      </div>
    </div>

    <!-- Overview Hole Selection Confirmation Popup -->
    <div class="overview-hole-popup" id="overview-popup">
      <div class="popup-left">
        <div class="popup-title" id="pop-hole-title">HOLE 12 • GOLDEN BELL</div>
        <div class="popup-meta" id="pop-hole-meta">Par 3 • 155 Yards • HCP 16</div>
      </div>
      <div class="popup-actions">
        <button class="popup-enter-btn" id="pop-btn-enter">View Hole ▶</button>
        <button class="popup-dismiss-btn" id="pop-btn-dismiss">✕</button>
      </div>
    </div>

    <!-- Map Zoom Controls -->
    <div class="map-controls">
      <button class="ctrl-btn" id="btn-zoom-in" title="Zoom In">+</button>
      <button class="ctrl-btn" id="btn-zoom-out" title="Zoom Out">−</button>
      <button class="ctrl-btn" id="btn-reset" title="Reset View">⟲</button>
    </div>

    <div id="tooltip"></div>
  </div>
</div>
</main>

<script>
  const COURSE = {data_json};

  let currentHoleIndex = 0; // 0 = Overview, 1..N = Hole 1..N
  let isHoleUp = true; // Hole-Up = working north towards the hole
  let isTargetingMode = false;
  let shotPoints = [];
  let currentViewBox = {{ x: 0, y: 0, w: 1000, h: 1000 }};
  let baseViewBox = {{ x: 0, y: 0, w: 1000, h: 1000 }};
  let selectedOverviewHole = null;

  const svg = document.getElementById('map-svg');
  const container = document.getElementById('map-container');
  const tooltip = document.getElementById('tooltip');
  const pillsBox = document.getElementById('pills-container');
  const overviewPopup = document.getElementById('overview-popup');
  const toggleBtn = document.getElementById('btn-toggle-view');

  // Build Header Navigation Pills
  const allBtn = document.createElement('button');
  allBtn.className = 'pill-btn active';
  allBtn.textContent = 'All Course';
  allBtn.onclick = () => selectHole(0);
  pillsBox.appendChild(allBtn);

  COURSE.holes.forEach((h, idx) => {{
    const btn = document.createElement('button');
    btn.className = 'pill-btn';
    btn.textContent = h.number;
    btn.title = `Hole ${{h.number}}: ${{h.name}}`;
    btn.onclick = () => selectHole(idx + 1);
    pillsBox.appendChild(btn);
  }});

  function selectHole(num) {{
    currentHoleIndex = num;
    shotPoints = [];
    isTargetingMode = false;
    updateModeBadge();
    dismissHolePopup();

    const pills = pillsBox.querySelectorAll('.pill-btn');
    pills.forEach((p, i) => p.classList.toggle('active', i === num));

    render();
  }}

  function clampViewBox(x, y, w, h, allowSoftMargin = false) {{
    // Hard lock on max zoom-out: strictly clamped at 1x (baseViewBox.w)
    const minW = baseViewBox.w / 8.0;
    const maxW = baseViewBox.w;
    const clampedW = Math.max(minW, Math.min(maxW, w));
    const ratio = baseViewBox.h / baseViewBox.w;
    const clampedH = clampedW * ratio;

    // When at 1x zoom (or Overview), permit only a subtle soft-lock nudge (~8% / .92x) before springing back
    if (clampedW >= baseViewBox.w * 0.999) {{
      const maxNudgeX = baseViewBox.w * (allowSoftMargin ? 0.08 : 0.0);
      const maxNudgeY = baseViewBox.h * (allowSoftMargin ? 0.08 : 0.0);
      const baseCenterX = baseViewBox.x + baseViewBox.w / 2;
      const baseCenterY = baseViewBox.y + baseViewBox.h / 2;

      let cx = x + clampedW / 2;
      let cy = y + clampedH / 2;
      cx = Math.max(baseCenterX - maxNudgeX, Math.min(baseCenterX + maxNudgeX, cx));
      cy = Math.max(baseCenterY - maxNudgeY, Math.min(baseCenterY + maxNudgeY, cy));

      return {{
        x: cx - clampedW / 2,
        y: cy - clampedH / 2,
        w: clampedW,
        h: clampedH
      }};
    }}

    // When zoomed in on a hole, permit smooth navigation within course bounds
    const baseCenterX = baseViewBox.x + baseViewBox.w / 2;
    const baseCenterY = baseViewBox.y + baseViewBox.h / 2;
    const maxOffsetX = (baseViewBox.w - clampedW) / 2 + (allowSoftMargin ? baseViewBox.w * 0.05 : 0);
    const maxOffsetY = (baseViewBox.h - clampedH) / 2 + (allowSoftMargin ? baseViewBox.h * 0.05 : 0);

    let cx = x + clampedW / 2;
    let cy = y + clampedH / 2;
    cx = Math.max(baseCenterX - maxOffsetX, Math.min(baseCenterX + maxOffsetX, cx));
    cy = Math.max(baseCenterY - maxOffsetY, Math.min(baseCenterY + maxOffsetY, cy));

    return {{
      x: cx - clampedW / 2,
      y: cy - clampedH / 2,
      w: clampedW,
      h: clampedH
    }};
  }}

  function updateViewBox(x, y, w, h, allowSoft = true) {{
    const clamped = clampViewBox(x, y, w, h, allowSoft);
    currentViewBox = clamped;
    svg.setAttribute('viewBox', `${{clamped.x}} ${{clamped.y}} ${{clamped.w}} ${{clamped.h}}`);
  }}

  let animationFrameId = null;
  function animateViewBoxTo(targetX, targetY, targetW, targetH, durationMs = 200) {{
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    const startX = currentViewBox.x;
    const startY = currentViewBox.y;
    const startW = currentViewBox.w;
    const startH = currentViewBox.h;
    const startTime = performance.now();

    function step(now) {{
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / durationMs);
      const ease = 0.5 - Math.cos(progress * Math.PI) / 2;

      const curX = startX + (targetX - startX) * ease;
      const curY = startY + (targetY - startY) * ease;
      const curW = startW + (targetW - startW) * ease;
      const curH = startH + (targetH - startH) * ease;

      currentViewBox = {{ x: curX, y: curY, w: curW, h: curH }};
      svg.setAttribute('viewBox', `${{curX}} ${{curY}} ${{curW}} ${{curH}}`);

      if (progress < 1.0) {{
        animationFrameId = requestAnimationFrame(step);
      }} else {{
        animationFrameId = null;
      }}
    }}
    animationFrameId = requestAnimationFrame(step);
  }}

  function snapBackToBounds() {{
    if (currentViewBox.w >= baseViewBox.w * 0.999) {{
      if (Math.hypot(currentViewBox.x - baseViewBox.x, currentViewBox.y - baseViewBox.y) > 0.5) {{
        animateViewBoxTo(baseViewBox.x, baseViewBox.y, baseViewBox.w, baseViewBox.h, 240);
      }}
    }} else {{
      const hard = clampViewBox(currentViewBox.x, currentViewBox.y, currentViewBox.w, currentViewBox.h, false);
      if (Math.hypot(hard.x - currentViewBox.x, hard.y - currentViewBox.y) > 2) {{
        animateViewBoxTo(hard.x, hard.y, hard.w, hard.h, 180);
      }}
    }}
  }}

  function updateModeBadge() {{
    const badge = document.getElementById('mode-badge');
    if (isTargetingMode) {{
      badge.textContent = '🎯 Target Mode';
      badge.className = 'mode-indicator target';
      container.classList.add('targeting');
    }} else {{
      badge.textContent = '🖐️ Pan Mode';
      badge.className = 'mode-indicator explore';
      container.classList.remove('targeting');
    }}
  }}

  function showHolePopup(holeNum) {{
    selectedOverviewHole = holeNum;
    const h = COURSE.holes[holeNum - 1];
    document.getElementById('pop-hole-title').textContent = `HOLE ${{h.number}} • ${{h.name.toUpperCase()}}`;
    document.getElementById('pop-hole-meta').textContent = `Par ${{h.par}} • ${{h.length_yards}} Yards • HCP ${{h.handicap}}`;
    document.getElementById('pop-btn-enter').textContent = `View Hole ${{h.number}} ▶`;
    overviewPopup.style.display = 'flex';
  }}

  function dismissHolePopup() {{
    overviewPopup.style.display = 'none';
    selectedOverviewHole = null;
  }}

  document.getElementById('pop-btn-enter').onclick = () => {{
    if (selectedOverviewHole) {{
      selectHole(selectedOverviewHole);
    }}
  }};

  document.getElementById('pop-btn-dismiss').onclick = dismissHolePopup;

  function render() {{
    const frameG = document.getElementById('layer-frame');
    const turfG = document.getElementById('layer-turf');
    const fwG = document.getElementById('layer-fairways');
    const greenG = document.getElementById('layer-green');
    const teeG = document.getElementById('layer-tees');
    const bunkerG = document.getElementById('layer-bunkers');
    const waterG = document.getElementById('layer-water');
    const lineG = document.getElementById('layer-lines');
    const arcG = document.getElementById('layer-arcs');
    const markerG = document.getElementById('layer-markers');
    const shotG = document.getElementById('layer-shots');
    const labelG = document.getElementById('layer-overview-labels');

    [frameG, turfG, fwG, greenG, teeG, bunkerG, waterG, lineG, arcG, markerG, shotG, labelG].forEach(g => g.innerHTML = '');

    if (currentHoleIndex === 0) {{
      // OVERVIEW MODE: True spatial course property map with continuous turf, tee spots, and property window
      document.getElementById('hole-card').style.display = 'none';
      document.getElementById('shot-planner-card').style.display = 'none';
      toggleBtn.style.display = 'none'; // In-window overlay button hidden in overview
      document.querySelector('.map-controls').style.display = 'none'; // Zoom buttons hidden in overview

      document.getElementById('plaque-title-text').textContent = `${{COURSE.course_name.toUpperCase()}} • PROPERTY OVERVIEW`;
      document.getElementById('stage-plaque-sub').textContent = `${{COURSE.total_holes}} HOLES • PAR ${{COURSE.total_par}} • ${{COURSE.total_yards}} YARDS`;

      const ov = COURSE.overview;
      const b = ov.bounds;
      baseViewBox = {{ x: b[0], y: b[1], w: b[2], h: b[3] }};
      updateViewBox(b[0], b[1], b[2], b[3]);

      // Property backdrop fill (provides deep turf color under all pan/zoom states)
      const frameRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      frameRect.setAttribute('x', b[0] - b[2]);
      frameRect.setAttribute('y', b[1] - b[3]);
      frameRect.setAttribute('width', b[2] * 3);
      frameRect.setAttribute('height', b[3] * 3);
      frameRect.setAttribute('fill', '#142017');
      frameG.appendChild(frameRect);

      // 2. Continuous Property-Wide Turf Rough (fills all gaps between holes)
      if (ov.turf_path) {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', ov.turf_path);
        p.setAttribute('fill', '#274724');
        p.setAttribute('stroke', '#335c2f');
        p.setAttribute('stroke-width', '1.5');
        p.setAttribute('fill-opacity', '0.96');
        turfG.appendChild(p);
      }}

      // 3. Water Hazards
      ov.waters.forEach(water => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', water.path);
        p.setAttribute('fill', '#2980b9');
        p.setAttribute('stroke', '#85c1e9');
        p.setAttribute('stroke-width', '1.5');
        waterG.appendChild(p);
      }});

      // 4. Fairways
      ov.fairways.forEach(fw => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', fw.path);
        p.setAttribute('fill', '#5b9a42');
        p.setAttribute('stroke', '#4e8838');
        p.setAttribute('stroke-width', '1.0');
        p.style.cursor = 'pointer';
        p.onclick = (e) => {{
          e.stopPropagation();
          showHolePopup(fw.hole);
        }};
        fwG.appendChild(p);
      }});

      // 5. Tee Boxes & Spots
      ov.tees.forEach(tee => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', tee.path);
        p.setAttribute('fill', '#3e7732');
        p.setAttribute('stroke', '#ffffff');
        p.setAttribute('stroke-width', '1.0');
        p.style.cursor = 'pointer';
        p.onclick = (e) => {{
          e.stopPropagation();
          showHolePopup(tee.hole);
        }};
        teeG.appendChild(p);

        // Tee Spot Marker
        if (tee.center) {{
          const spot = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          spot.setAttribute('x', tee.center[0] - 3.5);
          spot.setAttribute('y', tee.center[1] - 3.5);
          spot.setAttribute('width', '7');
          spot.setAttribute('height', '7');
          spot.setAttribute('fill', '#3498db');
          spot.setAttribute('stroke', '#ffffff');
          spot.setAttribute('stroke-width', '1.2');
          spot.style.cursor = 'pointer';
          spot.onclick = (e) => {{
            e.stopPropagation();
            showHolePopup(tee.hole);
          }};
          teeG.appendChild(spot);
        }}
      }});

      // 6. Bunkers
      ov.bunkers.forEach(bunker => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', bunker.path);
        p.setAttribute('fill', '#edd69a');
        p.setAttribute('stroke', '#bfa15f');
        p.setAttribute('stroke-width', '1.2');
        bunkerG.appendChild(p);
      }});

      // 7. Putting Greens
      ov.greens.forEach(green => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', green.path);
        p.setAttribute('fill', '#27ae60');
        p.setAttribute('stroke', '#2ecc71');
        p.setAttribute('stroke-width', '1.5');
        p.style.cursor = 'pointer';
        p.onclick = (e) => {{
          e.stopPropagation();
          showHolePopup(green.hole);
        }};
        greenG.appendChild(p);
      }});

      // 8. Centerlines
      ov.centerlines.forEach(cl => {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', cl.path);
        p.setAttribute('fill', 'none');
        p.setAttribute('stroke', '#ffffff');
        p.setAttribute('stroke-width', '1.5');
        p.setAttribute('stroke-dasharray', '5,5');
        p.setAttribute('stroke-opacity', '0.45');
        lineG.appendChild(p);
      }});

      // 9. Hole Badges
      ov.labels.forEach(lbl => {{
        const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        badgeG.style.cursor = 'pointer';
        badgeG.onclick = (e) => {{
          e.stopPropagation();
          showHolePopup(lbl.hole);
        }};

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', lbl.x);
        circle.setAttribute('cy', lbl.y);
        circle.setAttribute('r', '14');
        circle.setAttribute('fill', '#18241b');
        circle.setAttribute('stroke', '#2ecc71');
        circle.setAttribute('stroke-width', '2');
        badgeG.appendChild(circle);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', lbl.x);
        text.setAttribute('y', lbl.y + 4.5);
        text.setAttribute('fill', '#ecf0f1');
        text.setAttribute('font-size', '12');
        text.setAttribute('font-weight', 'bold');
        text.setAttribute('text-anchor', 'middle');
        text.textContent = lbl.hole;
        badgeG.appendChild(text);

        labelG.appendChild(badgeG);
      }});

      return;
    }}

    // HOLE VIEW MODE
    document.getElementById('hole-card').style.display = 'block';
    document.getElementById('shot-planner-card').style.display = 'flex';
    toggleBtn.style.display = 'flex'; // In-window overlay button visible in hole view
    document.querySelector('.map-controls').style.display = 'flex';
    toggleBtn.textContent = isHoleUp ? '🎯 Hole-Up' : '🧭 North-Up';

    const h = COURSE.holes[currentHoleIndex - 1];
    const modeKey = isHoleUp ? 'hole_up' : 'north';
    const paths = h.paths[modeKey];
    const pin = h.pin[modeKey];
    const tee = h.tee[modeKey];
    const bounds = isHoleUp ? h.bounds_hole_up : h.bounds_north;

    document.getElementById('plaque-title-text').textContent = `${{COURSE.course_name.toUpperCase()}} • HOLE ${{h.number}}`;
    document.getElementById('stage-plaque-sub').textContent = `${{h.name.toUpperCase()}} • PAR ${{h.par}} • ${{h.length_yards}} YDS • HCP ${{h.handicap || '--'}}`;

    document.getElementById('card-hole-num').textContent = `HOLE ${{h.number}}`;
    document.getElementById('card-hole-name').textContent = h.name.toUpperCase();
    document.getElementById('card-par').textContent = h.par;
    document.getElementById('card-yds').textContent = h.length_yards;
    document.getElementById('card-hcp').textContent = h.handicap || '--';

    baseViewBox = {{ x: bounds[0], y: bounds[1], w: bounds[2], h: bounds[3] }};
    updateViewBox(bounds[0], bounds[1], bounds[2], bounds[3]);

    // 1. Smart Continuous Turf Buffer
    if (paths.turf) {{
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', paths.turf);
      p.setAttribute('fill', '#2d5229');
      p.setAttribute('stroke', '#355e3b');
      p.setAttribute('stroke-width', '1.0');
      p.setAttribute('fill-opacity', '0.95');
      turfG.appendChild(p);
    }}

    // 2. Fairways
    paths.fairways.forEach(fPath => {{
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', fPath);
      p.setAttribute('fill', '#5b9a42');
      p.setAttribute('stroke', '#4e8838');
      p.setAttribute('stroke-width', '1.0');
      fwG.appendChild(p);
    }});

    // 3. Tees
    paths.tees.forEach(tPath => {{
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', tPath);
      p.setAttribute('fill', '#3e7732');
      p.setAttribute('stroke', '#ffffff');
      p.setAttribute('stroke-width', '1.2');
      teeG.appendChild(p);
    }});

    // 4. Green
    if (paths.green) {{
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', paths.green);
      p.setAttribute('fill', '#27ae60');
      p.setAttribute('stroke', '#2ecc71');
      p.setAttribute('stroke-width', '1.5');
      greenG.appendChild(p);
    }}

    // 5. Water Hazards
    h.waters.forEach(water => {{
      const pPath = isHoleUp ? water.path_hole_up : water.path_north;
      if (pPath) {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', pPath);
        p.setAttribute('fill', '#2980b9');
        p.setAttribute('stroke', '#85c1e9');
        p.setAttribute('stroke-width', '1.2');
        p.onmouseenter = (e) => showTooltip(e, `${{water.name}} • ${{water.dist_tee}} yds from tee`);
        p.onmouseleave = hideTooltip;
        waterG.appendChild(p);
      }}
    }});

    // 6. Bunkers
    h.bunkers.forEach(bunker => {{
      const pPath = isHoleUp ? bunker.path_hole_up : bunker.path_north;
      if (pPath) {{
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('d', pPath);
        p.setAttribute('fill', '#edd69a');
        p.setAttribute('stroke', '#bfa15f');
        p.setAttribute('stroke-width', '1.2');
        p.onmouseenter = (e) => showTooltip(e, `${{bunker.type.toUpperCase()}} BUNKER • ${{bunker.dist_tee}} yds carry • ${{bunker.dist_pin}} yds to pin`);
        p.onmouseleave = hideTooltip;
        bunkerG.appendChild(p);
      }}
    }});

    // 7. Centerline
    if (paths.centerline) {{
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', paths.centerline);
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', '#ffffff');
      p.setAttribute('stroke-width', '1.2');
      p.setAttribute('stroke-dasharray', '4,4');
      p.setAttribute('stroke-opacity', '0.45');
      lineG.appendChild(p);
    }}

    // 8. Yardage Arcs
    if (pin && pin.x !== undefined) {{
      [100, 150, 200, 250].forEach(arcYd => {{
        if (arcYd < h.length_yards) {{
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', pin.x);
          circle.setAttribute('cy', pin.y);
          circle.setAttribute('r', arcYd);
          circle.setAttribute('fill', 'none');
          circle.setAttribute('stroke', '#ffffff');
          circle.setAttribute('stroke-width', '0.8');
          circle.setAttribute('stroke-dasharray', '3,3');
          circle.setAttribute('stroke-opacity', '0.35');
          arcG.appendChild(circle);

          const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          txt.setAttribute('x', pin.x);
          // Inverted Y: place label between pin and tee (downwards towards tee)
          txt.setAttribute('y', pin.y + arcYd);
          txt.setAttribute('fill', '#ecf0f1');
          txt.setAttribute('font-size', '8');
          txt.setAttribute('font-weight', 'bold');
          txt.setAttribute('text-anchor', 'middle');
          txt.setAttribute('fill-opacity', '0.6');
          txt.textContent = arcYd;
          arcG.appendChild(txt);
        }}
      }});
    }}

    // 9. Pin Flag
    if (pin) {{
      const flagUse = document.createElementNS('http://www.w3.org/2000/svg', 'use');
      flagUse.setAttribute('href', '#flag-icon');
      flagUse.setAttribute('x', pin.x);
      flagUse.setAttribute('y', pin.y);
      markerG.appendChild(flagUse);
    }}

    // 10. Active Tee Marker
    if (tee) {{
      const teeUse = document.createElementNS('http://www.w3.org/2000/svg', 'use');
      teeUse.setAttribute('href', '#tee-icon');
      teeUse.setAttribute('x', tee.x);
      teeUse.setAttribute('y', tee.y);
      markerG.appendChild(teeUse);
    }}

    renderShots();
    updateShotPlannerUI();
  }}

  // Multi-Shot Rendering & Planning
  function renderShots() {{
    const shotG = document.getElementById('layer-shots');
    shotG.innerHTML = '';

    if (currentHoleIndex === 0 || shotPoints.length === 0) return;

    const h = COURSE.holes[currentHoleIndex - 1];
    const modeKey = isHoleUp ? 'hole_up' : 'north';
    const tee = h.tee[modeKey];
    const pin = h.pin[modeKey];

    let currentStart = tee;

    shotPoints.forEach((target, i) => {{
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', currentStart.x);
      line.setAttribute('y1', currentStart.y);
      line.setAttribute('x2', target.x);
      line.setAttribute('y2', target.y);
      line.setAttribute('stroke', '#f1c40f');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('stroke-dasharray', '5,3');
      shotG.appendChild(line);

      const markerGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      markerGroup.style.cursor = 'move';

      const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      ring.setAttribute('cx', target.x);
      ring.setAttribute('cy', target.y);
      ring.setAttribute('r', '14');
      ring.setAttribute('fill', 'rgba(241, 196, 15, 0.25)');
      ring.setAttribute('stroke', '#f1c40f');
      ring.setAttribute('stroke-width', '1.5');
      markerGroup.appendChild(ring);

      const centerDot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      centerDot.setAttribute('cx', target.x);
      centerDot.setAttribute('cy', target.y);
      centerDot.setAttribute('r', '3');
      centerDot.setAttribute('fill', '#f1c40f');
      markerGroup.appendChild(centerDot);

      const numText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      numText.setAttribute('x', target.x);
      numText.setAttribute('y', target.y + 4);
      numText.setAttribute('fill', '#ffffff');
      numText.setAttribute('font-size', '10');
      numText.setAttribute('font-weight', 'bold');
      numText.setAttribute('text-anchor', 'middle');
      numText.textContent = (i + 1);
      markerGroup.appendChild(numText);

      let isDragging = false;
      markerGroup.onmousedown = (e) => {{
        e.stopPropagation();
        isDragging = true;
      }};
      window.addEventListener('mousemove', (e) => {{
        if (!isDragging) return;
        const pt = getSvgCoords(e);
        shotPoints[i] = {{ x: pt.x, y: pt.y }};
        renderShots();
        updateShotPlannerUI();
      }});
      window.addEventListener('mouseup', () => {{ isDragging = false; }});

      shotG.appendChild(markerGroup);
      currentStart = target;
    }});

    // Dotted approach line from last target to pin (pointing towards the hole)
    if (shotPoints.length > 0 && pin) {{
      const lastTarget = shotPoints[shotPoints.length - 1];
      const approachLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      approachLine.setAttribute('x1', lastTarget.x);
      approachLine.setAttribute('y1', lastTarget.y);
      approachLine.setAttribute('x2', pin.x);
      approachLine.setAttribute('y2', pin.y);
      approachLine.setAttribute('stroke', '#e74c3c');
      approachLine.setAttribute('stroke-width', '2');
      approachLine.setAttribute('stroke-dasharray', '5,3');
      shotG.appendChild(approachLine);
    }}
  }}

  function updateShotPlannerUI() {{
    const shotList = document.getElementById('shot-list');

    if (currentHoleIndex === 0) return;

    if (shotPoints.length === 0) {{
      shotList.innerHTML = '<div class="empty-prompt">Click <strong>"🎯 Place Shot"</strong> below to drop your first shot target, or drag with your mouse to pan around.</div>';
      return;
    }}

    shotList.innerHTML = '';

    const h = COURSE.holes[currentHoleIndex - 1];
    const modeKey = isHoleUp ? 'hole_up' : 'north';
    const tee = h.tee[modeKey];
    const pin = h.pin[modeKey];

    let prevPoint = tee;
    shotPoints.forEach((pt, i) => {{
      const dist = Math.round(Math.hypot(pt.x - prevPoint.x, pt.y - prevPoint.y));
      const shotRow = document.createElement('div');
      shotRow.className = 'shot-row';
      shotRow.innerHTML = `
        <div class="shot-row-name">
          <span class="shot-badge">${{i + 1}}</span>
          <span>${{i === 0 ? 'Drive' : 'Shot ' + (i + 1)}}</span>
        </div>
        <div class="shot-row-val">${{dist}} yds</div>
      `;
      shotList.appendChild(shotRow);
      prevPoint = pt;
    }});

    // Remaining distance to pin from last shot
    if (pin && shotPoints.length > 0) {{
      const lastPt = shotPoints[shotPoints.length - 1];
      const remDist = Math.round(Math.hypot(pin.x - lastPt.x, pin.y - lastPt.y));
      const remRow = document.createElement('div');
      remRow.className = 'shot-row remaining-row';
      remRow.innerHTML = `
        <div class="shot-row-name">
          <span>🚩 To Pin</span>
        </div>
        <div class="shot-row-val">${{remDist}} yds</div>
      `;
      shotList.appendChild(remRow);
    }}
  }}

  function getSvgCoords(e) {{
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }}

  // Shot Planner Actions
  document.getElementById('btn-place-shot').onclick = () => {{
    isTargetingMode = true;
    updateModeBadge();
  }};

  document.getElementById('btn-toggle-pan').onclick = () => {{
    isTargetingMode = false;
    updateModeBadge();
  }};

  document.getElementById('btn-undo-shot').onclick = () => {{
    if (shotPoints.length > 0) {{
      shotPoints.pop();
      renderShots();
      updateShotPlannerUI();
    }}
  }};

  document.getElementById('btn-clear-shots').onclick = () => {{
    shotPoints = [];
    isTargetingMode = false;
    updateModeBadge();
    renderShots();
    updateShotPlannerUI();
  }};

  // In-Window Floating Orientation Toggle Button
  toggleBtn.onclick = () => {{
    isHoleUp = !isHoleUp;
    toggleBtn.textContent = isHoleUp ? '🎯 Hole-Up' : '🧭 North-Up';
    shotPoints = [];
    render();
  }};

  // Mouse Pan & Click Behavior
  let isPanning = false;
  let hasMoved = false;
  let startX = 0, startY = 0;
  let initialVbX = 0, initialVbY = 0;

  container.addEventListener('mousedown', (e) => {{
    if (e.target.closest('#shot-planner-card, .floating-card, .overview-hole-popup, .map-controls, .map-top-right')) return;

    if (!isTargetingMode) {{
      isPanning = true;
      hasMoved = false;
      container.classList.add('panning');
      startX = e.clientX;
      startY = e.clientY;
      initialVbX = currentViewBox.x;
      initialVbY = currentViewBox.y;
    }}
  }});

  window.addEventListener('mousemove', (e) => {{
    if (!isPanning) return;
    const dxPx = e.clientX - startX;
    const dyPx = e.clientY - startY;
    if (Math.hypot(dxPx, dyPx) > 4) hasMoved = true;

    // If at 1x zoom (hard-locked zoom level, including Course Overview):
    if (currentViewBox.w >= baseViewBox.w * 0.999) {{
      const maxNudgeX = baseViewBox.w * 0.08;
      const maxNudgeY = baseViewBox.h * 0.08;
      const scaleX = baseViewBox.w / svg.clientWidth;
      const scaleY = baseViewBox.h / svg.clientHeight;
      const rawDx = -dxPx * scaleX;
      const rawDy = -dyPx * scaleY;
      // Damped rubber-band curve (tanh) - moves the map inside the window just barely (~.92x)
      const dampedDx = maxNudgeX * Math.tanh(rawDx / (maxNudgeX * 2.2));
      const dampedDy = maxNudgeY * Math.tanh(rawDy / (maxNudgeY * 2.2));
      currentViewBox = {{
        x: baseViewBox.x + dampedDx,
        y: baseViewBox.y + dampedDy,
        w: baseViewBox.w,
        h: baseViewBox.h
      }};
      svg.setAttribute('viewBox', `${{currentViewBox.x}} ${{currentViewBox.y}} ${{currentViewBox.w}} ${{currentViewBox.h}}`);
      return;
    }}

    // When zoomed in:
    const scaleX = currentViewBox.w / svg.clientWidth;
    const scaleY = currentViewBox.h / svg.clientHeight;
    updateViewBox(initialVbX - dxPx * scaleX, initialVbY - dyPx * scaleY, currentViewBox.w, currentViewBox.h, true);
  }});

  window.addEventListener('mouseup', () => {{
    if (isPanning) {{
      isPanning = false;
      container.classList.remove('panning');
      snapBackToBounds();
    }}
  }});

  // Click on map
  svg.addEventListener('click', (e) => {{
    if (hasMoved) return;

    if (currentHoleIndex === 0) {{
      if (!e.target.closest('#overview-popup, #layer-overview-labels, path, rect')) {{
        dismissHolePopup();
      }}
      return;
    }}

    if (isTargetingMode) {{
      const pt = getSvgCoords(e);
      shotPoints.push({{ x: pt.x, y: pt.y }});
      renderShots();
      updateShotPlannerUI();
    }}
  }});

  // Map Zoom Controls
  document.getElementById('btn-zoom-in').onclick = () => {{
    const factor = 0.8;
    const newW = currentViewBox.w * factor;
    const newH = currentViewBox.h * factor;
    const newX = currentViewBox.x + (currentViewBox.w - newW) / 2;
    const newY = currentViewBox.y + (currentViewBox.h - newH) / 2;
    const clamped = clampViewBox(newX, newY, newW, newH, false);
    animateViewBoxTo(clamped.x, clamped.y, clamped.w, clamped.h, 150);
  }};

  document.getElementById('btn-zoom-out').onclick = () => {{
    const factor = 1.25;
    const newW = currentViewBox.w * factor;
    const newH = currentViewBox.h * factor;
    const newX = currentViewBox.x + (currentViewBox.w - newW) / 2;
    const newY = currentViewBox.y + (currentViewBox.h - newH) / 2;
    const clamped = clampViewBox(newX, newY, newW, newH, false);
    animateViewBoxTo(clamped.x, clamped.y, clamped.w, clamped.h, 150);
  }};

  document.getElementById('btn-reset').onclick = () => {{
    animateViewBoxTo(baseViewBox.x, baseViewBox.y, baseViewBox.w, baseViewBox.h, 240);
  }};

  // Mouse Wheel Zoom
  let wheelTimeout = null;
  container.addEventListener('wheel', (e) => {{
    e.preventDefault();
    // Hard lock on Overview at 1x zoom (no zooming in or out)
    if (currentHoleIndex === 0) return;

    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    const factor = e.deltaY > 0 ? 1.15 : 0.87;
    const pt = getSvgCoords(e);
    const newW = currentViewBox.w * factor;
    const newH = currentViewBox.h * factor;
    const newX = pt.x - (pt.x - currentViewBox.x) * factor;
    const newY = pt.y - (pt.y - currentViewBox.y) * factor;
    updateViewBox(newX, newY, newW, newH, false);

    clearTimeout(wheelTimeout);
    wheelTimeout = setTimeout(snapBackToBounds, 180);
  }}, {{ passive: false }});

  function showTooltip(e, text) {{
    tooltip.textContent = text;
    tooltip.style.left = e.clientX + 'px';
    tooltip.style.top = e.clientY + 'px';
    tooltip.style.display = 'block';
  }}

  function hideTooltip() {{
    tooltip.style.display = 'none';
  }}

  // Header Navigation (Static Layout)
  document.getElementById('btn-prev').onclick = () => {{
    if (currentHoleIndex > 1) selectHole(currentHoleIndex - 1);
    else selectHole(COURSE.holes.length);
  }};

  document.getElementById('btn-next').onclick = () => {{
    if (currentHoleIndex < COURSE.holes.length) selectHole(currentHoleIndex + 1);
    else selectHole(1);
  }};

  window.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight' || e.key === 'PageDown') document.getElementById('btn-next').click();
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') document.getElementById('btn-prev').click();
    if (e.key === 'Escape') {{
      isTargetingMode = false;
      updateModeBadge();
      dismissHolePopup();
    }}
  }});

  // Initial render: start on Course Overview
  selectHole(0);
</script>
</body>
</html>
"""
    return html


def export_interactive_html(
    course: GolfCourse,
    output_filepath: Union[str, Path],
    title: Optional[str] = None,
) -> Path:
    """Export an interactive HTML course viewer to disk."""
    out_path = Path(output_filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = generate_interactive_html(course, title=title)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out_path
