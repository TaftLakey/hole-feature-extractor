import React from 'react';
import { Point2D } from '../types/course';

export interface ShotPlannerProps {
  shots: Point2D[];
  tee: Point2D;
  pin: Point2D;
  isTargeting: boolean;
  onToggleTargeting: (targeting: boolean) => void;
  onUndo: () => void;
  onClear: () => void;
}

export const ShotPlanner: React.FC<ShotPlannerProps> = ({
  shots,
  tee,
  pin,
  isTargeting,
  onToggleTargeting,
  onUndo,
  onClear,
}) => {
  let prev = tee;
  const shotDistances = shots.map((pt) => {
    const dist = Math.round(Math.hypot(pt.x - prev.x, pt.y - prev.y));
    prev = pt;
    return dist;
  });

  const remainingDist =
    shots.length > 0 && pin
      ? Math.round(Math.hypot(pin.x - shots[shots.length - 1].x, pin.y - shots[shots.length - 1].y))
      : null;

  return (
    <div className="shot-planner-card" id="shot-planner-card">
      <div className="planner-header">
        <div className="planner-title-row">
          <span className="planner-title">Shot Planner</span>
          <span
            className={`mode-indicator ${isTargeting ? 'target' : 'explore'}`}
          >
            {isTargeting ? '🎯 Target Mode' : '🖐️ Pan Mode'}
          </span>
        </div>
        <button className="planner-clear-btn" onClick={onClear}>
          Clear All
        </button>
      </div>

      <div className="shot-list">
        {shots.length === 0 ? (
          <div className="empty-prompt">
            Click <strong>&quot;🎯 Place Shot&quot;</strong> below to drop your first shot target, or drag with your mouse to pan around.
          </div>
        ) : (
          <>
            {shots.map((_, i) => (
              <div key={i} className="shot-row">
                <div className="shot-row-name">
                  <span className="shot-badge">{i + 1}</span>
                  <span>{i === 0 ? 'Drive' : `Shot ${i + 1}`}</span>
                </div>
                <div className="shot-row-val">{shotDistances[i]} yds</div>
              </div>
            ))}
            {remainingDist !== null && (
              <div className="shot-row remaining-row">
                <div className="shot-row-name">
                  <span>🚩 To Pin</span>
                </div>
                <div className="shot-row-val">{remainingDist} yds</div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="planner-actions">
        <button
          className={`planner-btn ${isTargeting ? 'primary active' : 'primary'}`}
          onClick={() => onToggleTargeting(true)}
        >
          🎯 Place Shot
        </button>
        <button
          className={`planner-btn ${!isTargeting ? 'secondary active' : 'secondary'}`}
          onClick={() => onToggleTargeting(false)}
        >
          🖐️ Pan Mode
        </button>
        <button
          className="planner-btn secondary"
          onClick={onUndo}
          disabled={shots.length === 0}
        >
          Undo
        </button>
      </div>
    </div>
  );
};
