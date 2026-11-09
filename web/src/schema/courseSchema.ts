import { z } from 'zod';

export const Point2DSchema = z.object({
  x: z.number(),
  y: z.number(),
});

export const HolePinTeeSchema = z.object({
  hole_up: Point2DSchema,
  north: Point2DSchema,
});

export const HolePathSetSchema = z.object({
  turf: z.string().default(''),
  green: z.string().default(''),
  fairways: z.array(z.string()).default([]),
  tees: z.array(z.string()).default([]),
  centerline: z.string().default(''),
});

export const HolePathsSchema = z.object({
  hole_up: HolePathSetSchema,
  north: HolePathSetSchema,
});

export const HazardItemSchema = z.object({
  id: z.string().default(''),
  name: z.string().optional().nullable().default(''),
  type: z.string().optional().default('hazard'),
  dist_tee: z.number().optional().default(0),
  dist_pin: z.number().optional().default(0),
  path_hole_up: z.string().default(''),
  path_north: z.string().default(''),
});

export const HoleDataSchema = z.object({
  number: z.number(),
  name: z.string().default(''),
  par: z.number(),
  handicap: z.union([z.number(), z.string()]).optional().nullable(),
  length_yards: z.number(),
  rotation_deg: z.number().default(0),
  bounds_hole_up: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  bounds_north: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  pin: HolePinTeeSchema,
  tee: HolePinTeeSchema,
  paths: HolePathsSchema,
  bunkers: z.array(HazardItemSchema).default([]),
  waters: z.array(HazardItemSchema).default([]),
});

export const OverviewElementSchema = z.object({
  hole: z.number(),
  name: z.string().optional().nullable(),
  path: z.string().default(''),
  center: z.tuple([z.number(), z.number()]).optional(),
});

export const OverviewLabelSchema = z.object({
  hole: z.number(),
  x: z.number(),
  y: z.number(),
  name: z.string().default(''),
  par: z.number(),
  yards: z.number(),
  handicap: z.union([z.number(), z.string()]).default('--'),
});

export const CourseOverviewSchema = z.object({
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  turf_path: z.string().default(''),
  fairways: z.array(OverviewElementSchema).default([]),
  greens: z.array(OverviewElementSchema).default([]),
  tees: z.array(OverviewElementSchema).default([]),
  bunkers: z.array(OverviewElementSchema).default([]),
  waters: z.array(OverviewElementSchema).default([]),
  centerlines: z.array(OverviewElementSchema).default([]),
  labels: z.array(OverviewLabelSchema).default([]),
});

export const CourseDataSchema = z.object({
  course_name: z.string(),
  total_holes: z.number(),
  total_par: z.number(),
  total_yards: z.number(),
  overview: CourseOverviewSchema,
  holes: z.array(HoleDataSchema),
});

export const DataAttributionSchema = z.object({
  name: z.string(),
  url: z.string(),
  license: z.string(),
});

export const CourseIndexEntrySchema = z.object({
  slug: z.string(),
  name: z.string(),
  holes: z.number(),
  par: z.number(),
  yards: z.number(),
  tournaments: z.array(z.string()).default([]),
  data_file: z.string(),
});

export const CoursesIndexSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  data_attribution: DataAttributionSchema,
  courses: z.array(CourseIndexEntrySchema),
});
