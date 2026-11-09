import { z } from 'zod';
import {
  Point2DSchema,
  HolePinTeeSchema,
  HolePathSetSchema,
  HolePathsSchema,
  HazardItemSchema,
  HoleDataSchema,
  OverviewElementSchema,
  OverviewLabelSchema,
  CourseOverviewSchema,
  CourseDataSchema,
  DataAttributionSchema,
  CourseIndexEntrySchema,
  CoursesIndexSchema,
} from '../schema/courseSchema';

export type Point2D = z.infer<typeof Point2DSchema>;
export type HolePinTee = z.infer<typeof HolePinTeeSchema>;
export type HolePathSet = z.infer<typeof HolePathSetSchema>;
export type HolePaths = z.infer<typeof HolePathsSchema>;
export type HazardItem = z.infer<typeof HazardItemSchema>;
export type HoleData = z.infer<typeof HoleDataSchema>;
export type OverviewElement = z.infer<typeof OverviewElementSchema>;
export type OverviewLabel = z.infer<typeof OverviewLabelSchema>;
export type CourseOverview = z.infer<typeof CourseOverviewSchema>;
export type CourseData = z.infer<typeof CourseDataSchema>;
export type DataAttribution = z.infer<typeof DataAttributionSchema>;
export type CourseIndexEntry = z.infer<typeof CourseIndexEntrySchema>;
export type CoursesIndex = z.infer<typeof CoursesIndexSchema>;
