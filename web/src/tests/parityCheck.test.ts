import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { CourseDataSchema } from '../schema/courseSchema';

describe('Parity Verification Across All Shipped Courses', () => {
  const coursesDir = path.resolve(__dirname, '../../public/data/courses');
  const courseFiles = fs
    .readdirSync(coursesDir)
    .filter((f) => f.endsWith('.json'))
    .sort();

  for (const file of courseFiles) {
    describe(`Course: ${file}`, () => {
      const filePath = path.join(coursesDir, file);
      const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      const course = CourseDataSchema.parse(raw);

      it('has exactly 18 holes and valid overall course metrics', () => {
        expect(course.total_holes).toBe(18);
        expect(course.holes.length).toBe(18);
        expect(course.total_par).toBeGreaterThanOrEqual(70);
        expect(course.total_yards).toBeGreaterThanOrEqual(6500);
      });

      it('has valid overview bounds and overview paths', () => {
        expect(course.overview.bounds.length).toBe(4);
        expect(course.overview.bounds[2]).toBeGreaterThan(100);
        expect(course.overview.bounds[3]).toBeGreaterThan(100);
        expect(course.overview.turf_path.length).toBeGreaterThan(0);
        expect(course.overview.fairways.length).toBeGreaterThan(0);
        expect(course.overview.greens.length).toBe(18);
        expect(course.overview.labels.length).toBe(18);
      });

      it('confirms every hole has non-empty pin, tee, green, and bounds in both Hole-Up and North-Up', () => {
        for (const hole of course.holes) {
          // Hole-Up paths
          expect(hole.paths.hole_up.green.length).toBeGreaterThan(0);
          expect(Array.isArray(hole.paths.hole_up.fairways)).toBe(true);
          expect(hole.paths.hole_up.turf.length).toBeGreaterThan(0);

          // North-Up paths
          expect(hole.paths.north.green.length).toBeGreaterThan(0);
          expect(Array.isArray(hole.paths.north.fairways)).toBe(true);
          expect(hole.paths.north.turf.length).toBeGreaterThan(0);

          // Pin and Tee coordinates
          expect(typeof hole.pin.hole_up.x).toBe('number');
          expect(typeof hole.pin.hole_up.y).toBe('number');
          expect(typeof hole.pin.north.x).toBe('number');
          expect(typeof hole.pin.north.y).toBe('number');

          expect(typeof hole.tee.hole_up.x).toBe('number');
          expect(typeof hole.tee.hole_up.y).toBe('number');
          expect(typeof hole.tee.north.x).toBe('number');
          expect(typeof hole.tee.north.y).toBe('number');

          // Bounds
          expect(hole.bounds_hole_up[2]).toBeGreaterThan(0);
          expect(hole.bounds_hole_up[3]).toBeGreaterThan(0);
          expect(hole.bounds_north[2]).toBeGreaterThan(0);
          expect(hole.bounds_north[3]).toBeGreaterThan(0);

          // Hole-Up rotation check: pin is further up the hole than tee (smaller Y in SVG coords)
          expect(hole.pin.hole_up.y).toBeLessThan(hole.tee.hole_up.y);
        }
      });
    });
  }
});
