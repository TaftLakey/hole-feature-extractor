# Viewer Feature Parity Checklist

This checklist tracks 1:1 feature parity between the legacy HTML/JS viewer (`src/interactive_viewer.py` and `src/generate_course_viewers.py`) and the React + TypeScript web application.

---

## 1. Course Overview Mode
- [x] Whole-property SVG map rendered using property bounds (`bounds_north` / `overview.bounds`).
- [x] Background stage frame rect (`#142017`).
- [x] Continuous property-wide turf rough path (`#274724`, stroke `#335c2f`, 0.96 fill opacity).
- [x] Water hazard polygons (`#2980b9`, stroke `#85c1e9`).
- [x] Fairway polygons (`#5b9a42`, stroke `#4e8838`, pointer cursor).
- [x] Tee box polygons (`#3e7732`, stroke `#ffffff`) with blue square tee spots (`#3498db`).
- [x] Bunker polygons (`#edd69a`, stroke `#bfa15f`).
- [x] Putting green polygons (`#27ae60`, stroke `#2ecc71`, pointer cursor).
- [x] White dashed centerlines (`#ffffff`, dash 5,5, opacity 0.45).
- [x] Numbered circular hole badges (`#18241b`, green stroke `#2ecc71`, centered text).
- [x] Interactive overview popup on clicking fairway, green, tee, or badge:
  - [x] Displays `HOLE N • NAME`.
  - [x] Displays `Par X • Y Yards • HCP Z`.
  - [x] "View Hole N ▶" button transitions immediately to that hole.
  - [x] Dismiss button ("✕") and click-outside dismissal.
- [x] Overview mode hides hole card, shot planner, zoom controls, and orientation toggle.

---

## 2. Hole View Mode
- [x] Stage plaque header:
  - [x] Plaque glowing dot indicator.
  - [x] Course name in uppercase + `• HOLE N`.
  - [x] Subtitle: `NAME • PAR X • Y YDS • HCP Z`.
- [x] Floating hole card (top-left):
  - [x] Header: `HOLE N`.
  - [x] Subtitle: Hole name in uppercase.
  - [x] 3-stat grid: Par, Yards, HCP.
- [x] In-window orientation toggle button (top-right):
  - [x] Toggles between `🎯 Hole-Up` and `🧭 North-Up`.
  - [x] Swaps active path set (`paths.hole_up` vs `paths.north`).
  - [x] Swaps active pin/tee coordinates and viewBox bounds.
  - [x] Clears current shots upon toggle.
- [x] Layered SVG rendering order:
  1. `layer-frame`: Backdrop rect fill.
  2. `layer-turf`: Smart continuous turf buffer (`#2d5229`).
  3. `layer-fairways`: Fairways (`#5b9a42`).
  4. `layer-tees`: Tee polygons (`#3e7732`).
  5. `layer-green`: Putting green (`#27ae60`).
  6. `layer-water`: Water hazards (`#2980b9`).
  7. `layer-bunkers`: Sand traps (`#edd69a`).
  8. `layer-lines`: Centerline dashed line (`#ffffff`, dash 4,4, opacity 0.45).
  9. `layer-arcs`: Distance arcs from pin (100, 150, 200, 250 yds) with bold yardage labels.
  10. `layer-markers`: Tee marker (`#3498db` rect) and pin flag (`#flag-icon` red pennant + white base).
  11. `layer-shots`: Interactive multi-shot lines, draggable target markers, and red approach line to pin.
- [x] Hazard hover tooltips:
  - [x] Water: `${name} • ${dist_tee} yds from tee`.
  - [x] Bunker: `${bunker.type.toUpperCase()} BUNKER • ${dist_tee} yds carry • ${dist_pin} yds to pin`.

---

## 3. Pan and Zoom Engine (`usePanZoom`)
- [x] Drag-to-pan in Pan Mode with smooth movement.
- [x] Cursor indicates grab/grabbing state.
- [x] Mouse wheel zoom anchored at pointer coordinates.
- [x] Onscreen zoom controls (bottom-right): Zoom In (`+`), Zoom Out (`−`), and Reset (`⟲`).
- [x] Clamping:
  - [x] Max zoom-out hard-locked to 1x (`baseViewBox.w`).
  - [x] Soft margin damping (rubber-band tanh curve) when dragging near boundaries.
  - [x] Animated snap-back to bounds on mouse release (`snapBackToBounds`).
- [x] Smooth animated viewBox transitions (`animateViewBoxTo`) respecting `prefers-reduced-motion`.
- [x] Zoom locked on Course Overview (overview stays centered at 1x with subtle nudge damping).

---

## 4. Multi-Shot Planner (Session-Only)
- [x] Floating shot planner card (bottom-left) visible in hole view.
- [x] Mode badge indicates current state ("🖐️ Pan Mode" vs "🎯 Target Mode").
- [x] "🎯 Place Shot" button activates targeting mode.
- [x] "🖐️ Pan Mode" button returns to pan mode.
- [x] Clicking on map in targeting mode places sequential shot targets (1, 2, 3...).
- [x] Draggable shot markers:
  - [x] Pulsing gold ring (`rgba(241, 196, 15, 0.25)`), border (`#f1c40f`), and center dot.
  - [x] Centered shot number (1, 2, 3...).
  - [x] Mouse drag updates coordinates smoothly.
- [x] Shot lines:
  - [x] Dashed gold line (`#f1c40f`, dash 5,3) connecting tee to Shot 1 and intermediate shots.
  - [x] Dashed red line (`#e74c3c`, dash 5,3) connecting final shot target to pin flag.
- [x] Shot list stats:
  - [x] Drive distance in yards (Tee to Shot 1).
  - [x] Intermediate shot distances in yards.
  - [x] "🚩 To Pin" remaining distance in yards.
- [x] "Undo" button removes latest shot target.
- [x] "Clear All" button resets shot planner.
- [x] Shot state resets automatically on hole change or orientation toggle.
- [x] **Strict session-only**: No persistence to `localStorage`, `sessionStorage`, or URL parameters.

---

## 5. Navigation & Keyboard Shortcuts
- [x] Header course plaque: Course title, total holes, par, total yardage.
- [x] Navigation pills: "All Course" + individual hole pills (1..18).
- [x] Active hole pill highlighting.
- [x] Header action buttons: "◀ Prev" and "Next ▶" with cycling.
- [x] Keyboard shortcuts:
  - [x] `ArrowRight` or `PageDown`: Next Hole.
  - [x] `ArrowLeft` or `PageUp`: Prev Hole.
  - [x] `Escape`: Cancel targeting mode / dismiss overview popup.
  - [x] Shortcuts do not hijack typing in text fields or modal dialogs.

---

## 6. Course Picker / Dashboard Landing Page
- [x] Dashboard landing page listing all available courses.
- [x] Course cards showing:
  - [x] Course name.
  - [x] Tournament tags (Masters, U.S. Open, PGA Championship, The Players, etc.).
  - [x] Badges for hole count, total par, and total yardage.
- [x] Single-click navigation to course viewer.
- [x] Clean back-navigation button to return to course picker.

---

## 7. Performance & Safety
- [x] Lazy-load courses: only `courses.json` index loaded upfront; individual course JSON fetched on selection.
- [x] Pure SVG rendering without `dangerouslySetInnerHTML`.
- [x] Schema validation with Zod upon loading course JSON.
- [x] Visible OpenStreetMap attribution linking to `https://www.openstreetmap.org/copyright`.
- [x] Strict Content-Security-Policy configured for GitHub Pages static host.
- [x] All 4 target courses render without missing greens, tees, or pins:
  - [x] Augusta National Golf Club
  - [x] Pebble Beach Golf Links
  - [x] Quail Hollow Club
  - [x] TPC Sawgrass (THE PLAYERS Stadium Course)
