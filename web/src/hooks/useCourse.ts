import { useEffect, useState, useRef, useCallback } from 'react';
import { CourseData, CoursesIndex } from '../types/course';
import { CourseDataSchema, CoursesIndexSchema } from '../schema/courseSchema';

export function useCourse(activeSlug: string | null) {
  const [index, setIndex] = useState<CoursesIndex | null>(null);
  const [indexLoading, setIndexLoading] = useState<boolean>(true);
  const [indexError, setIndexError] = useState<string | null>(null);

  const [activeCourse, setActiveCourse] = useState<CourseData | null>(null);
  const [courseLoading, setCourseLoading] = useState<boolean>(false);
  const [courseError, setCourseError] = useState<string | null>(null);

  // In-memory cache for loaded courses
  const cacheRef = useRef<Map<string, CourseData>>(new Map());

  // Fetch index
  const fetchIndex = useCallback(async () => {
    setIndexLoading(true);
    setIndexError(null);
    try {
      const res = await fetch('./data/courses.json');
      if (!res.ok) {
        throw new Error(`Failed to load courses index (HTTP ${res.status})`);
      }
      const raw = await res.json();
      const validated = CoursesIndexSchema.parse(raw);
      setIndex(validated);
    } catch (err: any) {
      setIndexError(err.message || 'Error loading courses index');
    } finally {
      setIndexLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndex();
  }, [fetchIndex]);

  // Fetch course when activeSlug changes
  useEffect(() => {
    if (!activeSlug) {
      setActiveCourse(null);
      setCourseError(null);
      setCourseLoading(false);
      return;
    }

    if (cacheRef.current.has(activeSlug)) {
      setActiveCourse(cacheRef.current.get(activeSlug)!);
      setCourseError(null);
      setCourseLoading(false);
      return;
    }

    let isMounted = true;
    setCourseLoading(true);
    setCourseError(null);

    async function loadCourse() {
      try {
        const res = await fetch(`./data/courses/${activeSlug}.json`);
        if (!res.ok) {
          throw new Error(`Failed to load course '${activeSlug}' (HTTP ${res.status})`);
        }
        const raw = await res.json();
        const validated = CourseDataSchema.parse(raw);

        if (isMounted) {
          cacheRef.current.set(activeSlug!, validated);
          setActiveCourse(validated);
        }
      } catch (err: any) {
        if (isMounted) {
          setCourseError(err.message || `Failed to parse data for course '${activeSlug}'`);
        }
      } finally {
        if (isMounted) {
          setCourseLoading(false);
        }
      }
    }

    loadCourse();

    return () => {
      isMounted = false;
    };
  }, [activeSlug]);

  return {
    index,
    indexLoading,
    indexError,
    activeCourse,
    courseLoading,
    courseError,
    retryFetchIndex: fetchIndex,
  };
}
