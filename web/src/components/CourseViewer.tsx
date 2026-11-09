import React, { useState, useRef, useCallback } from 'react';
import { CourseData, Point2D, HoleData } from '../types/course';
import { CourseHeader } from './CourseHeader';
import { HoleCard } from './HoleCard';
import { OverviewPopup } from './OverviewPopup';
import { ShotPlanner } from './ShotPlanner';
import { ZoomControls } from './ZoomControls';
import { Tooltip, TooltipState } from './Tooltip';
import { usePanZoom } from '../hooks/usePanZoom';
import { useKeyboardNav } from '../hooks/useKeyboardNav';

interface CourseViewerProps {
  course: CourseData;
  currentHole: number; // 0 = overview, 1..N = hole
  onSelectHole: (hole: number) => void;
  onBackToPicker: () => void;
}

export const CourseViewer: React.FC<CourseViewerProps> = ({
  course,
  currentHole,
  onSelectHole,
  onBackToPicker,
}) => {
  const [isHoleUp, setIsHoleUp] = useState<boolean>(true);
  const [isTargeting, setIsTargeting] = useState<boolean>(false);
  const [shots, setShots] = useState<Point2D[]>([]);
  const [selectedOverviewHole, setSelectedOverviewHole] = useState<HoleData | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    text: '',
    x: 0,
    y: 0,
  });

  const svgRef = useRef<SVGSVGElement | null>(null);
  const draggingShotIdx = useRef<number | null>(null);

  const activeHoleData = currentHole > 0 ? course.holes[currentHole - 1] : null;
  const isOverview = currentHole === 0;

  // Base bounds for active view
  let baseBounds: [number, number, number, number] = [0, 0, 1000, 1000];
  if (isOverview) {
    baseBounds = course.overview.bounds;
  } else if (activeHoleData) {
    baseBounds = isHoleUp ? activeHoleData.bounds_hole_up : activeHoleData.bounds_north;
  }

  // Pan and Zoom engine
  const {
    viewBoxString,
    zoomIn,
    zoomOut,
    resetView,
    handleMouseDown,
    handleWheel,
  } = usePanZoom(baseBounds, isOverview, isTargeting);

  // Clear shots and targeting when hole or orientation changes
  const handleSelectHoleInternal = useCallback(
    (h: number) => {
      setShots([]);
      setIsTargeting(false);
      setSelectedOverviewHole(null);
      setTooltip((t) => ({ ...t, visible: false }));
      onSelectHole(h);
    },
    [onSelectHole]
  );

  const handleToggleOrientation = useCallback(() => {
    setIsHoleUp((prev) => !prev);
    setShots([]);
  }, []);

  // Keyboard navigation
  useKeyboardNav({
    onNextHole: () => {
      const total = course.holes.length;
      if (currentHole >= total) {
        handleSelectHoleInternal(1);
      } else {
        handleSelectHoleInternal(currentHole + 1);
      }
    },
    onPrevHole: () => {
      const total = course.holes.length;
      if (currentHole <= 1) {
        handleSelectHoleInternal(total);
      } else {
        handleSelectHoleInternal(currentHole - 1);
      }
    },
    onEscape: () => {
      setIsTargeting(false);
      setSelectedOverviewHole(null);
    },
  });

  // SVG coordinate transformation helper
  const getSvgCoordinates = (clientX: number, clientY: number): Point2D => {
    if (!svgRef.current) return { x: 0, y: 0 };
    const pt = svgRef.current.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const transformed = pt.matrixTransform(svgRef.current.getScreenCTM()?.inverse());
    return { x: transformed.x, y: transformed.y };
  };

  // Map Click for placing shots
  const handleMapClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isTargeting || isOverview) return;
    const pt = getSvgCoordinates(e.clientX, e.clientY);
    setShots((prev) => [...prev, pt]);
  };

  // Draggable Shot Markers
  const handleShotMarkerMouseDown = (e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    draggingShotIdx.current = idx;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (draggingShotIdx.current === null) return;
      const pt = getSvgCoordinates(moveEvent.clientX, moveEvent.clientY);
      setShots((prev) => {
        const next = [...prev];
        next[draggingShotIdx.current!] = pt;
        return next;
      });
    };

    const handleMouseUp = () => {
      draggingShotIdx.current = null;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const modeKey = isHoleUp ? 'hole_up' : 'north';
  const activePin = activeHoleData?.pin[modeKey] || { x: 0, y: 0 };
  const activeTee = activeHoleData?.tee[modeKey] || { x: 0, y: 0 };

  return (
    <div className="viewer-container">
      <CourseHeader
        course={course}
        currentHole={currentHole}
        onSelectHole={handleSelectHoleInternal}
        onBackToPicker={onBackToPicker}
      />

      <main className="stage-wrapper">
        <div className="course-stage-frame">
          {/* Plaque Header */}
          <div className="stage-plaque-header">
            <div className="stage-plaque-title">
              <span className="plaque-dot" />
              <span>
                {course.course_name.toUpperCase()} &bull;{' '}
                {isOverview ? 'PROPERTY OVERVIEW' : `HOLE ${currentHole}`}
              </span>
            </div>
            <div className="stage-plaque-sub">
              {isOverview
                ? `${course.total_holes} HOLES • PAR ${course.total_par} • ${course.total_yards.toLocaleString()} YARDS`
                : `${activeHoleData?.name.toUpperCase()} • PAR ${activeHoleData?.par} • ${activeHoleData?.length_yards} YDS • HCP ${activeHoleData?.handicap || '--'}`}
            </div>
          </div>

          <div
            className={`map-container ${isTargeting ? 'targeting' : ''}`}
            onMouseDown={handleMouseDown}
          >
            {/* Top Right: In-Window Orientation Toggle (Hole View only) */}
            {!isOverview && (
              <div className="map-top-right">
                <button
                  className="overlay-btn"
                  onClick={handleToggleOrientation}
                  title="Toggle Hole-Up / North-Up"
                >
                  {isHoleUp ? '🎯 Hole-Up' : '🧭 North-Up'}
                </button>
              </div>
            )}

            {/* Top Left: Floating Hole Info Card (Hole View only) */}
            {!isOverview && activeHoleData && (
              <HoleCard hole={activeHoleData} />
            )}

            {/* Bottom Left: Shot Planner (Hole View only) */}
            {!isOverview && activeHoleData && (
              <ShotPlanner
                shots={shots}
                tee={activeTee}
                pin={activePin}
                isTargeting={isTargeting}
                onToggleTargeting={setIsTargeting}
                onUndo={() => setShots((s) => s.slice(0, -1))}
                onClear={() => {
                  setShots([]);
                  setIsTargeting(false);
                }}
              />
            )}

            {/* Overview Hole Selection Popup */}
            {isOverview && (
              <OverviewPopup
                hole={selectedOverviewHole}
                onEnterHole={(h) => handleSelectHoleInternal(h)}
                onDismiss={() => setSelectedOverviewHole(null)}
              />
            )}

            {/* Bottom Right: Zoom Controls */}
            <ZoomControls
              onZoomIn={zoomIn}
              onZoomOut={zoomOut}
              onReset={resetView}
            />

            {/* Hazard Tooltip */}
            <Tooltip tooltip={tooltip} />

            {/* SVG Stage */}
            <svg
              ref={svgRef}
              className="map-svg"
              viewBox={viewBoxString}
              preserveAspectRatio="xMidYMid meet"
              onClick={handleMapClick}
              onWheel={handleWheel}
            >
              <defs>
                <g id="flag-icon">
                  <line x1="0" y1="0" x2="0" y2="-14" stroke="#e74c3c" strokeWidth="2.2" />
                  <polygon points="0,-14 9,-9 0,-5" fill="#e74c3c" />
                  <circle cx="0" cy="0" r="3.5" fill="#ffffff" stroke="#c0392b" strokeWidth="1.5" />
                </g>
                <g id="tee-icon">
                  <rect x="-4" y="-4" width="8" height="8" fill="#3498db" stroke="#ffffff" strokeWidth="1.5" />
                </g>
              </defs>

              {/* OVERVIEW MODE */}
              {isOverview && (
                <g className="overview-layers">
                  {/* Backdrop */}
                  <rect
                    x={course.overview.bounds[0] - course.overview.bounds[2]}
                    y={course.overview.bounds[1] - course.overview.bounds[3]}
                    width={course.overview.bounds[2] * 3}
                    height={course.overview.bounds[3] * 3}
                    fill="#142017"
                  />

                  {/* Turf Rough */}
                  {course.overview.turf_path && (
                    <path
                      d={course.overview.turf_path}
                      fill="#274724"
                      stroke="#335c2f"
                      strokeWidth="1.5"
                      fillOpacity="0.96"
                    />
                  )}

                  {/* Water Hazards */}
                  {course.overview.waters.map((w, idx) => (
                    <path
                      key={idx}
                      d={w.path}
                      fill="#2980b9"
                      stroke="#85c1e9"
                      strokeWidth="1.5"
                    />
                  ))}

                  {/* Fairways */}
                  {course.overview.fairways.map((fw, idx) => (
                    <path
                      key={idx}
                      d={fw.path}
                      fill="#5b9a42"
                      stroke="#4e8838"
                      strokeWidth="1.0"
                      style={{ cursor: 'pointer' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOverviewHole(course.holes[fw.hole - 1]);
                      }}
                    />
                  ))}

                  {/* Tees */}
                  {course.overview.tees.map((tee, idx) => (
                    <g key={idx}>
                      <path
                        d={tee.path}
                        fill="#3e7732"
                        stroke="#ffffff"
                        strokeWidth="1.0"
                        style={{ cursor: 'pointer' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedOverviewHole(course.holes[tee.hole - 1]);
                        }}
                      />
                      {tee.center && (
                        <rect
                          x={tee.center[0] - 3.5}
                          y={tee.center[1] - 3.5}
                          width="7"
                          height="7"
                          fill="#3498db"
                          stroke="#ffffff"
                          strokeWidth="1.2"
                          style={{ cursor: 'pointer' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedOverviewHole(course.holes[tee.hole - 1]);
                          }}
                        />
                      )}
                    </g>
                  ))}

                  {/* Bunkers */}
                  {course.overview.bunkers.map((b, idx) => (
                    <path
                      key={idx}
                      d={b.path}
                      fill="#edd69a"
                      stroke="#bfa15f"
                      strokeWidth="1.2"
                    />
                  ))}

                  {/* Greens */}
                  {course.overview.greens.map((gr, idx) => (
                    <path
                      key={idx}
                      d={gr.path}
                      fill="#27ae60"
                      stroke="#2ecc71"
                      strokeWidth="1.5"
                      style={{ cursor: 'pointer' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOverviewHole(course.holes[gr.hole - 1]);
                      }}
                    />
                  ))}

                  {/* Centerlines */}
                  {course.overview.centerlines.map((cl, idx) => (
                    <path
                      key={idx}
                      d={cl.path}
                      fill="none"
                      stroke="#ffffff"
                      strokeWidth="1.5"
                      strokeDasharray="5,5"
                      strokeOpacity="0.45"
                    />
                  ))}

                  {/* Hole Badges */}
                  {course.overview.labels.map((lbl) => (
                    <g
                      key={lbl.hole}
                      style={{ cursor: 'pointer' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedOverviewHole(course.holes[lbl.hole - 1]);
                      }}
                    >
                      <circle
                        cx={lbl.x}
                        cy={lbl.y}
                        r="14"
                        fill="#18241b"
                        stroke="#2ecc71"
                        strokeWidth="2"
                      />
                      <text
                        x={lbl.x}
                        y={lbl.y + 4.5}
                        fill="#ecf0f1"
                        fontSize="12"
                        fontWeight="bold"
                        textAnchor="middle"
                      >
                        {lbl.hole}
                      </text>
                    </g>
                  ))}
                </g>
              )}

              {/* HOLE VIEW MODE */}
              {!isOverview && activeHoleData && (
                <g className="hole-layers">
                  {/* Backdrop */}
                  <rect
                    x={baseBounds[0] - baseBounds[2]}
                    y={baseBounds[1] - baseBounds[3]}
                    width={baseBounds[2] * 3}
                    height={baseBounds[3] * 3}
                    fill="#142017"
                  />

                  {/* Smart Turf Buffer */}
                  {activeHoleData.paths[modeKey].turf && (
                    <path
                      d={activeHoleData.paths[modeKey].turf}
                      fill="#2d5229"
                      stroke="#355e3b"
                      strokeWidth="1.0"
                      fillOpacity="0.95"
                    />
                  )}

                  {/* Fairways */}
                  {activeHoleData.paths[modeKey].fairways.map((fwPath, idx) => (
                    <path
                      key={idx}
                      d={fwPath}
                      fill="#5b9a42"
                      stroke="#4e8838"
                      strokeWidth="1.0"
                    />
                  ))}

                  {/* Tees */}
                  {activeHoleData.paths[modeKey].tees.map((teePath, idx) => (
                    <path
                      key={idx}
                      d={teePath}
                      fill="#3e7732"
                      stroke="#ffffff"
                      strokeWidth="1.2"
                    />
                  ))}

                  {/* Green */}
                  {activeHoleData.paths[modeKey].green && (
                    <path
                      d={activeHoleData.paths[modeKey].green}
                      fill="#27ae60"
                      stroke="#2ecc71"
                      strokeWidth="1.5"
                    />
                  )}

                  {/* Water Hazards with Tooltips */}
                  {activeHoleData.waters.map((w, idx) => {
                    const p = isHoleUp ? w.path_hole_up : w.path_north;
                    return p ? (
                      <path
                        key={idx}
                        d={p}
                        fill="#2980b9"
                        stroke="#85c1e9"
                        strokeWidth="1.2"
                        onMouseEnter={(e) => {
                          setTooltip({
                            visible: true,
                            text: `${w.name || 'Water Hazard'} • ${w.dist_tee || 0} yds from tee`,
                            x: e.clientX,
                            y: e.clientY,
                          });
                        }}
                        onMouseLeave={() => setTooltip((t) => ({ ...t, visible: false }))}
                      />
                    ) : null;
                  })}

                  {/* Bunkers with Tooltips */}
                  {activeHoleData.bunkers.map((b, idx) => {
                    const p = isHoleUp ? b.path_hole_up : b.path_north;
                    return p ? (
                      <path
                        key={idx}
                        d={p}
                        fill="#edd69a"
                        stroke="#bfa15f"
                        strokeWidth="1.2"
                        onMouseEnter={(e) => {
                          setTooltip({
                            visible: true,
                            text: `${(b.type || 'fairway').toUpperCase()} BUNKER • ${b.dist_tee || 0} yds carry • ${b.dist_pin || 0} yds to pin`,
                            x: e.clientX,
                            y: e.clientY,
                          });
                        }}
                        onMouseLeave={() => setTooltip((t) => ({ ...t, visible: false }))}
                      />
                    ) : null;
                  })}

                  {/* Centerline */}
                  {activeHoleData.paths[modeKey].centerline && (
                    <path
                      d={activeHoleData.paths[modeKey].centerline}
                      fill="none"
                      stroke="#ffffff"
                      strokeWidth="1.2"
                      strokeDasharray="4,4"
                      strokeOpacity="0.45"
                    />
                  )}

                  {/* Yardage Arcs */}
                  {activePin && activePin.x !== undefined && (
                    <g className="yardage-arcs">
                      {[100, 150, 200, 250].map((arcYd) => {
                        if (arcYd >= activeHoleData.length_yards) return null;
                        return (
                          <g key={arcYd}>
                            <circle
                              cx={activePin.x}
                              cy={activePin.y}
                              r={arcYd}
                              fill="none"
                              stroke="#ffffff"
                              strokeWidth="0.8"
                              strokeDasharray="3,3"
                              strokeOpacity="0.35"
                            />
                            <text
                              x={activePin.x}
                              y={activePin.y + arcYd}
                              fill="#ecf0f1"
                              fontSize="8"
                              fontWeight="bold"
                              textAnchor="middle"
                              fillOpacity="0.6"
                            >
                              {arcYd}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  )}

                  {/* Pin Flag */}
                  <use
                    href="#flag-icon"
                    x={activePin.x}
                    y={activePin.y}
                  />

                  {/* Active Tee Marker */}
                  <use
                    href="#tee-icon"
                    x={activeTee.x}
                    y={activeTee.y}
                  />

                  {/* Multi-Shot Planner Interactive Layer */}
                  {shots.length > 0 && (
                    <g className="shot-layer">
                      {/* Shot Lines */}
                      {shots.map((target, i) => {
                        const start = i === 0 ? activeTee : shots[i - 1];
                        return (
                          <line
                            key={`shot-line-${i}`}
                            x1={start.x}
                            y1={start.y}
                            x2={target.x}
                            y2={target.y}
                            stroke="#f1c40f"
                            strokeWidth="2"
                            strokeDasharray="5,3"
                          />
                        );
                      })}

                      {/* Approach Line to Pin */}
                      <line
                        x1={shots[shots.length - 1].x}
                        y1={shots[shots.length - 1].y}
                        x2={activePin.x}
                        y2={activePin.y}
                        stroke="#e74c3c"
                        strokeWidth="2"
                        strokeDasharray="5,3"
                      />

                      {/* Draggable Shot Target Rings */}
                      {shots.map((target, i) => (
                        <g
                          key={`shot-target-${i}`}
                          style={{ cursor: 'move' }}
                          onMouseDown={(e) => handleShotMarkerMouseDown(e, i)}
                        >
                          <circle
                            cx={target.x}
                            cy={target.y}
                            r="14"
                            fill="rgba(241, 196, 15, 0.25)"
                            stroke="#f1c40f"
                            strokeWidth="1.5"
                          />
                          <circle
                            cx={target.x}
                            cy={target.y}
                            r="3"
                            fill="#f1c40f"
                          />
                          <text
                            x={target.x}
                            y={target.y + 4}
                            fill="#ffffff"
                            fontSize="10"
                            fontWeight="bold"
                            textAnchor="middle"
                          >
                            {i + 1}
                          </text>
                        </g>
                      ))}
                    </g>
                  )}
                </g>
              )}
            </svg>
          </div>
        </div>
      </main>
    </div>
  );
};
