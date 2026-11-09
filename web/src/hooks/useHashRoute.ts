import { useEffect, useState, useCallback } from 'react';

export interface RouteState {
  view: 'picker' | 'course';
  courseSlug: string | null;
  holeNumber: number; // 0 = overview, 1..N = hole N
}

function parseHash(hash: string): RouteState {
  // Strip leading '#' or '#/'
  const cleaned = hash.replace(/^#\/?/, '').trim();
  if (!cleaned) {
    return { view: 'picker', courseSlug: null, holeNumber: 0 };
  }

  // Format: course/<slug> or course/<slug>/hole/<num>
  const parts = cleaned.split('/');
  if (parts[0] === 'course' && parts[1]) {
    const courseSlug = parts[1];
    let holeNumber = 0;
    if (parts[2] === 'hole' && parts[3]) {
      const parsedHole = parseInt(parts[3], 10);
      if (!isNaN(parsedHole) && parsedHole >= 0) {
        holeNumber = parsedHole;
      }
    }
    return { view: 'course', courseSlug, holeNumber };
  }

  return { view: 'picker', courseSlug: null, holeNumber: 0 };
}

export function useHashRoute() {
  const [route, setRoute] = useState<RouteState>(() => parseHash(window.location.hash));

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(parseHash(window.location.hash));
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateToPicker = useCallback(() => {
    window.location.hash = '#/';
  }, []);

  const navigateToCourse = useCallback((slug: string, hole: number = 0) => {
    if (hole <= 0) {
      window.location.hash = `#/course/${slug}`;
    } else {
      window.location.hash = `#/course/${slug}/hole/${hole}`;
    }
  }, []);

  const navigateToHole = useCallback((hole: number) => {
    if (!route.courseSlug) return;
    if (hole <= 0) {
      window.location.hash = `#/course/${route.courseSlug}`;
    } else {
      window.location.hash = `#/course/${route.courseSlug}/hole/${hole}`;
    }
  }, [route.courseSlug]);

  return {
    route,
    navigateToPicker,
    navigateToCourse,
    navigateToHole,
  };
}
