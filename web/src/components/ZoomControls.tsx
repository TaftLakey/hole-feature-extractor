import React from 'react';

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export const ZoomControls: React.FC<ZoomControlsProps> = ({
  onZoomIn,
  onZoomOut,
  onReset,
}) => {
  return (
    <div className="map-controls">
      <button className="ctrl-btn" onClick={onZoomIn} title="Zoom In" aria-label="Zoom In">
        +
      </button>
      <button className="ctrl-btn" onClick={onZoomOut} title="Zoom Out" aria-label="Zoom Out">
        &minus;
      </button>
      <button className="ctrl-btn" onClick={onReset} title="Reset View" aria-label="Reset View">
        &#x27F2;
      </button>
    </div>
  );
};
