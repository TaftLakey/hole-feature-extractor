import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ShotPlanner } from '../components/ShotPlanner';
import { Point2D } from '../types/course';

describe('ShotPlanner Component', () => {
  const tee: Point2D = { x: 0, y: 400 };
  const pin: Point2D = { x: 0, y: 0 };

  it('renders empty prompt when no shots are placed', () => {
    render(
      <ShotPlanner
        shots={[]}
        tee={tee}
        pin={pin}
        isTargeting={false}
        onToggleTargeting={vi.fn()}
        onUndo={vi.fn()}
        onClear={vi.fn()}
      />
    );

    expect(screen.getByText(/Click/i)).toBeInTheDocument();
    expect(screen.getAllByText('🖐️ Pan Mode').length).toBe(2);
  });

  it('calculates shot distances and remaining distance to pin accurately', () => {
    // Shot 1 at (0, 150): 250 yds from tee (0, 400).
    // Remaining to pin (0, 0): 150 yds.
    const shots: Point2D[] = [{ x: 0, y: 150 }];

    render(
      <ShotPlanner
        shots={shots}
        tee={tee}
        pin={pin}
        isTargeting={true}
        onToggleTargeting={vi.fn()}
        onUndo={vi.fn()}
        onClear={vi.fn()}
      />
    );

    expect(screen.getByText('Drive')).toBeInTheDocument();
    expect(screen.getByText('250 yds')).toBeInTheDocument();
    expect(screen.getByText('🚩 To Pin')).toBeInTheDocument();
    expect(screen.getByText('150 yds')).toBeInTheDocument();
  });

  it('calculates multi-shot sequence accurately', () => {
    // Tee at (0, 400)
    // Shot 1 at (0, 150) -> Drive: 250 yds
    // Shot 2 at (0, 20) -> Shot 2: 130 yds
    // Pin at (0, 0) -> Remaining: 20 yds
    const shots: Point2D[] = [
      { x: 0, y: 150 },
      { x: 0, y: 20 },
    ];

    render(
      <ShotPlanner
        shots={shots}
        tee={tee}
        pin={pin}
        isTargeting={false}
        onToggleTargeting={vi.fn()}
        onUndo={vi.fn()}
        onClear={vi.fn()}
      />
    );

    expect(screen.getByText('Drive')).toBeInTheDocument();
    expect(screen.getByText('250 yds')).toBeInTheDocument();
    expect(screen.getByText('Shot 2')).toBeInTheDocument();
    expect(screen.getByText('130 yds')).toBeInTheDocument();
    expect(screen.getByText('🚩 To Pin')).toBeInTheDocument();
    expect(screen.getByText('20 yds')).toBeInTheDocument();
  });

  it('triggers onUndo, onClear, and onToggleTargeting handlers', () => {
    const handleToggle = vi.fn();
    const handleUndo = vi.fn();
    const handleClear = vi.fn();

    render(
      <ShotPlanner
        shots={[{ x: 0, y: 150 }]}
        tee={tee}
        pin={pin}
        isTargeting={false}
        onToggleTargeting={handleToggle}
        onUndo={handleUndo}
        onClear={handleClear}
      />
    );

    // Place shot button
    fireEvent.click(screen.getByText('🎯 Place Shot'));
    expect(handleToggle).toHaveBeenCalledWith(true);

    // Undo button
    fireEvent.click(screen.getByText('Undo'));
    expect(handleUndo).toHaveBeenCalled();

    // Clear all button
    fireEvent.click(screen.getByText('Clear All'));
    expect(handleClear).toHaveBeenCalled();
  });
});
