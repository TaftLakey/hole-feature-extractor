import { describe, it, expect } from 'vitest';
import { clampViewBox, ViewBox } from '../hooks/usePanZoom';

describe('usePanZoom - clampViewBox', () => {
  const baseViewBox: ViewBox = {
    x: 100,
    y: 200,
    w: 1000,
    h: 800,
  };

  it('clamps max zoom out at exactly baseViewBox.w', () => {
    // Attempt to zoom out beyond base width (e.g. w = 2000)
    const result = clampViewBox(100, 200, 2000, 1600, baseViewBox, false);
    expect(result.w).toBe(1000);
    expect(result.h).toBe(800);
    expect(result.x).toBe(100);
    expect(result.y).toBe(200);
  });

  it('clamps min zoom in at baseViewBox.w / 8', () => {
    // Attempt to zoom in closer than 1/8th width (e.g. w = 50)
    const result = clampViewBox(500, 500, 50, 40, baseViewBox, false);
    expect(result.w).toBe(125); // 1000 / 8 = 125
    expect(result.h).toBe(100); // 800 / 8 = 100
  });

  it('allows soft margin nudging when allowSoftMargin is true at 1x zoom', () => {
    // Nudge slightly outside bounds
    const hard = clampViewBox(300, 200, 1000, 800, baseViewBox, false);
    const soft = clampViewBox(300, 200, 1000, 800, baseViewBox, true);

    // Hard clamp locks to center (x = 100)
    expect(hard.x).toBe(100);
    // Soft clamp allows up to 8% nudge (up to x = 180)
    expect(soft.x).toBeGreaterThan(100);
    expect(soft.x).toBeLessThanOrEqual(180);
  });

  it('keeps viewBox centered when zoomed in within bounds', () => {
    const result = clampViewBox(500, 500, 500, 400, baseViewBox, false);
    expect(result.w).toBe(500);
    expect(result.h).toBe(400);
    // Center point is preserved within bounds
    expect(result.x).toBeGreaterThanOrEqual(baseViewBox.x);
    expect(result.x + result.w).toBeLessThanOrEqual(baseViewBox.x + baseViewBox.w);
  });
});
