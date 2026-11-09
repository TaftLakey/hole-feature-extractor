import React from 'react';
import { CoursesIndex } from '../types/course';

interface CoursePickerProps {
  index: CoursesIndex | null;
  loading: boolean;
  error: string | null;
  onSelectCourse: (slug: string) => void;
  onRetry: () => void;
}

export const CoursePicker: React.FC<CoursePickerProps> = ({
  index,
  loading,
  error,
  onSelectCourse,
  onRetry,
}) => {
  return (
    <div className="picker-container">
      <header className="picker-header">
        <div className="picker-brand">
          <span className="brand-flag" aria-hidden="true">🚩</span>
          <div>
            <h1 className="brand-title">PGA Tour Course Viewer</h1>
            <p className="brand-subtitle">Vector yardage books &amp; hole-by-hole routing</p>
          </div>
        </div>
      </header>

      <main className="picker-main">
        {loading && (
          <div className="status-container" role="status">
            <div className="spinner" />
            <p>Loading championship courses...</p>
          </div>
        )}

        {error && (
          <div className="status-container error" role="alert">
            <p className="error-title">Unable to load courses</p>
            <p className="error-desc">{error}</p>
            <button className="action-btn" onClick={onRetry}>
              Retry Loading
            </button>
          </div>
        )}

        {!loading && !error && index && (
          <div className="courses-grid" role="list">
            {index.courses.map((course) => (
              <div
                key={course.slug}
                className="course-card"
                role="listitem"
                tabIndex={0}
                onClick={() => onSelectCourse(course.slug)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectCourse(course.slug);
                  }
                }}
              >
                <div className="card-top">
                  {course.tournaments.length > 0 && (
                    <div className="tournament-tag">{course.tournaments[0]}</div>
                  )}
                  <h2 className="card-title">{course.name}</h2>
                </div>

                <div className="card-meta">
                  <span className="badge badge-holes">{course.holes} Holes</span>
                  <span className="meta-stat">Par {course.par}</span>
                  <span className="meta-stat">{course.yards.toLocaleString()} yds</span>
                </div>

                <div className="card-footer">
                  <span className="launch-text">Open Interactive Yardage Book &rarr;</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <footer className="site-footer">
        <p>
          Map data &copy;{' '}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenStreetMap contributors
          </a>{' '}
          under ODbL 1.0 &bull; Built with vector geometry engine
        </p>
      </footer>
    </div>
  );
};
