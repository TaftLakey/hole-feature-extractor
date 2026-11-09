import { describe, it, expect } from 'vitest';
import { CourseDataSchema, CoursesIndexSchema } from '../schema/courseSchema';
import fs from 'fs';
import path from 'path';

describe('Zod Schema Validation', () => {
  it('validates courses.json index schema', () => {
    const indexPath = path.resolve(__dirname, '../../public/data/courses.json');
    const raw = JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
    const parsed = CoursesIndexSchema.parse(raw);
    expect(parsed.courses.length).toBeGreaterThanOrEqual(4);
    expect(parsed.data_attribution.name).toBe('OpenStreetMap contributors');
  });

  it('validates all generated course JSON files', () => {
    const coursesDir = path.resolve(__dirname, '../../public/data/courses');
    const files = fs.readdirSync(coursesDir).filter((f) => f.endsWith('.json'));
    expect(files.length).toBeGreaterThanOrEqual(4);

    for (const file of files) {
      const filePath = path.join(coursesDir, file);
      const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      const parsed = CourseDataSchema.parse(raw);
      expect(parsed.total_holes).toBe(18);
      expect(parsed.holes.length).toBe(18);
      expect(parsed.overview.bounds.length).toBe(4);
      expect(parsed.overview.bounds[2]).toBeGreaterThan(0);
      expect(parsed.overview.bounds[3]).toBeGreaterThan(0);
    }
  });

  it('rejects malformed course data', () => {
    expect(() => {
      CourseDataSchema.parse({
        course_name: 'Broken Course',
        total_holes: 1,
        // missing required fields
      });
    }).toThrow();
  });
});
