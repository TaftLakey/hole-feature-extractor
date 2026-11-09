import React from 'react';
import { HoleData } from '../types/course';

interface OverviewPopupProps {
  hole: HoleData | null;
  onEnterHole: (holeNumber: number) => void;
  onDismiss: () => void;
}

export const OverviewPopup: React.FC<OverviewPopupProps> = ({
  hole,
  onEnterHole,
  onDismiss,
}) => {
  if (!hole) return null;

  return (
    <div className="overview-hole-popup" role="dialog" aria-modal="true">
      <div className="popup-left">
        <div className="popup-title">
          HOLE {hole.number} &bull; {hole.name.toUpperCase()}
        </div>
        <div className="popup-meta">
          Par {hole.par} &bull; {hole.length_yards} Yards &bull; HCP {hole.handicap || '--'}
        </div>
      </div>
      <div className="popup-actions">
        <button
          className="popup-enter-btn"
          onClick={() => onEnterHole(hole.number)}
        >
          View Hole {hole.number} &#x25B6;
        </button>
        <button
          className="popup-dismiss-btn"
          onClick={onDismiss}
          title="Dismiss"
          aria-label="Dismiss popup"
        >
          &times;
        </button>
      </div>
    </div>
  );
};
