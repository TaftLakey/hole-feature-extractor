import { useState, useRef, useEffect, useCallback } from 'react';

export interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function clampViewBox(
  x: number,
  y: number,
  w: number,
  _h: number,
  baseViewBox: ViewBox,
  allowSoftMargin: boolean = false
): ViewBox {
  const minW = baseViewBox.w / 8.0;
  const maxW = baseViewBox.w;
  const clampedW = Math.max(minW, Math.min(maxW, w));
  const ratio = baseViewBox.h / baseViewBox.w;
  const clampedH = clampedW * ratio;

  if (clampedW >= baseViewBox.w * 0.999) {
    const maxNudgeX = baseViewBox.w * (allowSoftMargin ? 0.08 : 0.0);
    const maxNudgeY = baseViewBox.h * (allowSoftMargin ? 0.08 : 0.0);
    const baseCenterX = baseViewBox.x + baseViewBox.w / 2;
    const baseCenterY = baseViewBox.y + baseViewBox.h / 2;

    let cx = x + clampedW / 2;
    let cy = y + clampedH / 2;
    cx = Math.max(baseCenterX - maxNudgeX, Math.min(baseCenterX + maxNudgeX, cx));
    cy = Math.max(baseCenterY - maxNudgeY, Math.min(baseCenterY + maxNudgeY, cy));

    return {
      x: cx - clampedW / 2,
      y: cy - clampedH / 2,
      w: clampedW,
      h: clampedH,
    };
  }

  const baseCenterX = baseViewBox.x + baseViewBox.w / 2;
  const baseCenterY = baseViewBox.y + baseViewBox.h / 2;
  const maxOffsetX = (baseViewBox.w - clampedW) / 2 + (allowSoftMargin ? baseViewBox.w * 0.05 : 0);
  const maxOffsetY = (baseViewBox.h - clampedH) / 2 + (allowSoftMargin ? baseViewBox.h * 0.05 : 0);

  let cx = x + clampedW / 2;
  let cy = y + clampedH / 2;
  cx = Math.max(baseCenterX - maxOffsetX, Math.min(baseCenterX + maxOffsetX, cx));
  cy = Math.max(baseCenterY - maxOffsetY, Math.min(baseCenterY + maxOffsetY, cy));

  return {
    x: cx - clampedW / 2,
    y: cy - clampedH / 2,
    w: clampedW,
    h: clampedH,
  };
}

export function usePanZoom(
  baseBounds: [number, number, number, number],
  _isOverview: boolean,
  isTargeting: boolean
) {
  const baseViewBox: ViewBox = {
    x: baseBounds[0],
    y: baseBounds[1],
    w: baseBounds[2],
    h: baseBounds[3],
  };

  const [currentViewBox, setCurrentViewBox] = useState<ViewBox>(baseViewBox);
  const viewBoxRef = useRef<ViewBox>(baseViewBox);
  viewBoxRef.current = currentViewBox;

  const baseRef = useRef<ViewBox>(baseViewBox);
  baseRef.current = baseViewBox;

  const animFrameRef = useRef<number | null>(null);
  const isPanningRef = useRef<boolean>(false);
  const panStartRef = useRef<{ clientX: number; clientY: number; vbX: number; vbY: number }>({
    clientX: 0,
    clientY: 0,
    vbX: baseBounds[0],
    vbY: baseBounds[1],
  });

  // Reset to baseViewBox whenever baseBounds change
  useEffect(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    setCurrentViewBox({
      x: baseBounds[0],
      y: baseBounds[1],
      w: baseBounds[2],
      h: baseBounds[3],
    });
  }, [baseBounds[0], baseBounds[1], baseBounds[2], baseBounds[3]]);

  const animateTo = useCallback((target: ViewBox, durationMs: number = 180) => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);

    // Respect prefers-reduced-motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || durationMs <= 0) {
      setCurrentViewBox(target);
      return;
    }

    const start = viewBoxRef.current;
    const startTime = performance.now();

    function step(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / durationMs);
      const ease = 0.5 - Math.cos(progress * Math.PI) / 2;

      const nextVb: ViewBox = {
        x: start.x + (target.x - start.x) * ease,
        y: start.y + (target.y - start.y) * ease,
        w: start.w + (target.w - start.w) * ease,
        h: start.h + (target.h - start.h) * ease,
      };

      setCurrentViewBox(nextVb);

      if (progress < 1.0) {
        animFrameRef.current = requestAnimationFrame(step);
      } else {
        animFrameRef.current = null;
      }
    }

    animFrameRef.current = requestAnimationFrame(step);
  }, []);

  const snapBackToBounds = useCallback(() => {
    const cur = viewBoxRef.current;
    const base = baseRef.current;

    if (cur.w >= base.w * 0.999) {
      if (Math.hypot(cur.x - base.x, cur.y - base.y) > 0.5) {
        animateTo(base, 240);
      }
    } else {
      const hard = clampViewBox(cur.x, cur.y, cur.w, cur.h, base, false);
      if (Math.hypot(hard.x - cur.x, hard.y - cur.y) > 2) {
        animateTo(hard, 180);
      }
    }
  }, [animateTo]);

  // Zoom In / Out / Reset
  const zoomIn = useCallback(() => {
    const factor = 0.8;
    const cur = viewBoxRef.current;
    const base = baseRef.current;
    const newW = cur.w * factor;
    const newH = cur.h * factor;
    const newX = cur.x + (cur.w - newW) / 2;
    const newY = cur.y + (cur.h - newH) / 2;
    const clamped = clampViewBox(newX, newY, newW, newH, base, false);
    animateTo(clamped, 150);
  }, [animateTo]);

  const zoomOut = useCallback(() => {
    const factor = 1.25;
    const cur = viewBoxRef.current;
    const base = baseRef.current;
    const newW = cur.w * factor;
    const newH = cur.h * factor;
    const newX = cur.x + (cur.w - newW) / 2;
    const newY = cur.y + (cur.h - newH) / 2;
    const clamped = clampViewBox(newX, newY, newW, newH, base, false);
    animateTo(clamped, 150);
  }, [animateTo]);

  const resetView = useCallback(() => {
    animateTo(baseRef.current, 240);
  }, [animateTo]);

  // Mouse drag pan handler
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (isTargeting) return;
      if (e.button !== 0) return; // Left click only

      isPanningRef.current = true;
      panStartRef.current = {
        clientX: e.clientX,
        clientY: e.clientY,
        vbX: viewBoxRef.current.x,
        vbY: viewBoxRef.current.y,
      };
    },
    [isTargeting]
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isPanningRef.current) return;
      const base = baseRef.current;
      const cur = viewBoxRef.current;
      const dxPx = e.clientX - panStartRef.current.clientX;
      const dyPx = e.clientY - panStartRef.current.clientY;

      if (cur.w >= base.w * 0.999) {
        // Subtle tanh rubber-band damping at 1x
        const maxNudgeX = base.w * 0.08;
        const maxNudgeY = base.h * 0.08;
        const scaleX = base.w / (window.innerWidth || 1000);
        const scaleY = base.h / (window.innerHeight || 1000);
        const rawDx = -dxPx * scaleX;
        const rawDy = -dyPx * scaleY;
        const dampedDx = maxNudgeX * Math.tanh(rawDx / (maxNudgeX * 2.2));
        const dampedDy = maxNudgeY * Math.tanh(rawDy / (maxNudgeY * 2.2));

        setCurrentViewBox({
          x: base.x + dampedDx,
          y: base.y + dampedDy,
          w: base.w,
          h: base.h,
        });
        return;
      }

      // Zoomed in
      const scaleX = cur.w / (window.innerWidth || 1000);
      const scaleY = cur.h / (window.innerHeight || 1000);
      const targetX = panStartRef.current.vbX - dxPx * scaleX;
      const targetY = panStartRef.current.vbY - dyPx * scaleY;
      const clamped = clampViewBox(targetX, targetY, cur.w, cur.h, base, true);
      setCurrentViewBox(clamped);
    };

    const handleMouseUp = () => {
      if (isPanningRef.current) {
        isPanningRef.current = false;
        snapBackToBounds();
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [snapBackToBounds]);

  // Wheel zoom handler
  const handleWheel = useCallback(
    (e: React.WheelEvent<SVGSVGElement>) => {
      e.preventDefault();

      const factor = e.deltaY > 0 ? 1.15 : 0.87;
      const svg = e.currentTarget;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(svg.getScreenCTM()?.inverse());

      const cur = viewBoxRef.current;
      const base = baseRef.current;
      const newW = cur.w * factor;
      const newH = cur.h * factor;
      const newX = svgPt.x - (svgPt.x - cur.x) * factor;
      const newY = svgPt.y - (svgPt.y - cur.y) * factor;

      const clamped = clampViewBox(newX, newY, newW, newH, base, false);
      setCurrentViewBox(clamped);
    },
    []
  );

  return {
    viewBoxString: `${currentViewBox.x} ${currentViewBox.y} ${currentViewBox.w} ${currentViewBox.h}`,
    currentViewBox,
    zoomIn,
    zoomOut,
    resetView,
    handleMouseDown,
    handleWheel,
  };
}
