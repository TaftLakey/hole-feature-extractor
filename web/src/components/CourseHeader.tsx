import React from 'react';
import { CourseData } from '../types/course';

interface CourseHeaderProps {
  course: CourseData;
  currentHole: number; // 0 = overview, 1..N = hole N
  onSelectHole: (hole: number) => void;
  onBackToPicker: () => void;
}

export const CourseHeader: React.FC<CourseHeaderProps> = ({
  course,
  currentHole,
  onSelectHole,
  onBackToPicker,
}) => {
  const totalHoles = course.holes.length;

  const handlePrev = () => {
    if (currentHole <= 1) {
      onSelectHole(totalHoles);
    } else {
      onSelectHole(currentHole - 1);
    }
  };

  const handleNext = () => {
    if (currentHole >= totalHoles) {
      onSelectHole(1);
    } else {
      onSelectHole(currentHole + 1);
    }
  };

  return (
    <header className="viewer-header">
      <div className="header-left">
        <button
          className="back-btn"
          onClick={onBackToPicker}
          title="Back to Course Selection"
        >
          &larr; Courses
        </button>
        <div>
          <div className="course-title">{course.course_name}</div>
          <div className="course-meta">
            {course.total_holes} Holes &bull; Par {course.total_par} &bull;{' '}
            {course.total_yards.toLocaleString()} Yards
          </div>
        </div>
      </div>

      <nav className="hole-pills" aria-label="Hole Navigation">
        <button
          className={`pill-btn ${currentHole === 0 ? 'active' : ''}`}
          onClick={() => onSelectHole(0)}
        >
          All Course
        </button>
        {course.holes.map((h) => (
          <button
            key={h.number}
            className={`pill-btn ${currentHole === h.number ? 'active' : ''}`}
            onClick={() => onSelectHole(h.number)}
            title={`Hole ${h.number}: ${h.name}`}
          >
            {h.number}
          </button>
        ))}
      </nav>

      <div className="header-actions">
        <button className="action-btn" onClick={handlePrev} title="Previous Hole">
          &#x25C0; Prev
        </button>
        <button className="action-btn" onClick={handleNext} title="Next Hole">
          Next &#x25B6;
        </button>
      </div>
    </header>
  );
};
