import React from 'react';
import { HoleData } from '../types/course';

interface HoleCardProps {
  hole: HoleData;
}

export const HoleCard: React.FC<HoleCardProps> = ({ hole }) => {
  return (
    <div className="floating-card" id="hole-card">
      <div className="hole-header">HOLE {hole.number}</div>
      <div className="hole-sub">{hole.name.toUpperCase()}</div>
      <div className="stat-grid">
        <div className="stat-item">
          <div className="stat-val">{hole.par}</div>
          <div className="stat-label">Par</div>
        </div>
        <div className="stat-item">
          <div className="stat-val">{hole.length_yards}</div>
          <div className="stat-label">Yards</div>
        </div>
        <div className="stat-item">
          <div className="stat-val">{hole.handicap || '--'}</div>
          <div className="stat-label">HCP</div>
        </div>
      </div>
    </div>
  );
};
