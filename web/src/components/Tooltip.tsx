import React from 'react';

export interface TooltipState {
  visible: boolean;
  text: string;
  x: number;
  y: number;
}

interface TooltipProps {
  tooltip: TooltipState;
}

export const Tooltip: React.FC<TooltipProps> = ({ tooltip }) => {
  if (!tooltip.visible) return null;

  return (
    <div
      className="custom-tooltip"
      style={{
        left: `${tooltip.x + 12}px`,
        top: `${tooltip.y + 12}px`,
      }}
    >
      {tooltip.text}
    </div>
  );
};
