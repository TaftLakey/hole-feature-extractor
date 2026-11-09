import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CourseHeader } from '../components/CourseHeader';
import { CourseData } from '../types/course';

const mockCourse: CourseData = {
  course_name: 'Torrey Pines Golf Course (South Course)',
  total_holes: 18,
  total_par: 72,
  total_yards: 7759,
  overview: {
    bounds: [0, 0, 1000, 1000],
    turf_path: 'M0,0 Z',
    fairways: [],
    greens: [],
    labels: [],
  },
  holes: Array.from({ length: 18 }, (_, i) => ({
    number: i + 1,
    name: `Hole ${i + 1}`,
    par: 4,
    handicap: i + 1,
    length_yards: 400,
    rotation_deg: 0,
    bounds_hole_up: [0, 0, 200, 500] as [number, number, number, number],
    bounds_north: [0, 0, 200, 500] as [number, number, number, number],
    pin: { hole_up: { x: 100, y: 50 }, north: { x: 100, y: 50 } },
    tee: { hole_up: { x: 100, y: 450 }, north: { x: 100, y: 450 } },
    paths: {
      hole_up: { turf: 'M0,0 Z', green: 'M0,0 Z', fairways: [] },
      north: { turf: 'M0,0 Z', green: 'M0,0 Z', fairways: [] },
    },
    bunkers: [],
    waters: [],
  })),
};

describe('CourseViewer Layout & Header Updates', () => {
  it('CourseHeader renders back button and hole navigation without top bar course title', () => {
    const handleSelectHole = vi.fn();
    const handleBack = vi.fn();

    render(
      <CourseHeader
        course={mockCourse}
        currentHole={0}
        onSelectHole={handleSelectHole}
        onBackToPicker={handleBack}
      />
    );

    // Back button exists
    expect(screen.getByText('← Courses')).toBeDefined();

    // Course title is no longer in the top header bar
    expect(screen.queryByText('Torrey Pines Golf Course (South Course)')).toBeNull();

    // Hole navigation pills are present
    expect(screen.getByText('All Course')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(screen.getByText('18')).toBeDefined();

    // Prev / Next actions exist
    expect(screen.getByTitle('Previous Hole')).toBeDefined();
    expect(screen.getByTitle('Next Hole')).toBeDefined();
  });
});
