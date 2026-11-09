import React from 'react';
import { useHashRoute } from './hooks/useHashRoute';
import { useCourse } from './hooks/useCourse';
import { CoursePicker } from './components/CoursePicker';
import { CourseViewer } from './components/CourseViewer';

export const App: React.FC = () => {
  const { route, navigateToPicker, navigateToCourse, navigateToHole } = useHashRoute();
  const {
    index,
    indexLoading,
    indexError,
    activeCourse,
    courseLoading,
    courseError,
    retryFetchIndex,
  } = useCourse(route.courseSlug);

  // Picker View
  if (route.view === 'picker' || !route.courseSlug) {
    return (
      <CoursePicker
        index={index}
        loading={indexLoading}
        error={indexError}
        onSelectCourse={(slug) => navigateToCourse(slug, 0)}
        onRetry={retryFetchIndex}
      />
    );
  }

  // Course Loading State
  if (courseLoading) {
    return (
      <div className="status-container fullscreen" role="status">
        <div className="spinner" />
        <p>Loading course data...</p>
      </div>
    );
  }

  // Course Error State
  if (courseError || !activeCourse) {
    return (
      <div className="status-container fullscreen error" role="alert">
        <p className="error-title">Course Not Found</p>
        <p className="error-desc">{courseError || `Unable to load course '${route.courseSlug}'`}</p>
        <button className="action-btn" onClick={navigateToPicker}>
          &larr; Back to Course List
        </button>
      </div>
    );
  }

  // Course Viewer View
  return (
    <CourseViewer
      course={activeCourse}
      currentHole={route.holeNumber}
      onSelectHole={(h) => navigateToHole(h)}
      onBackToPicker={navigateToPicker}
    />
  );
};
