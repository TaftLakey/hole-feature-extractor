import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CoursePicker } from '../components/CoursePicker';
import { CoursesIndex } from '../types/course';

const mockIndex: CoursesIndex = {
  schema_version: '1.0.0',
  generated_at: '2026-11-09T10:00:00Z',
  data_attribution: {
    name: 'OpenStreetMap contributors',
    url: 'https://www.openstreetmap.org/copyright',
    license: 'ODbL 1.0',
  },
  courses: [
    {
      slug: 'augusta_national_golf_club',
      name: 'Augusta National Golf Club',
      holes: 18,
      par: 72,
      yards: 7595,
      tournaments: ['Masters Tournament'],
      data_file: 'courses/augusta_national_golf_club.json',
    },
    {
      slug: 'pebble_beach_golf_links',
      name: 'Pebble Beach Golf Links',
      holes: 18,
      par: 72,
      yards: 7033,
      tournaments: ['AT&T Pebble Beach Pro-Am'],
      data_file: 'courses/pebble_beach_golf_links.json',
    },
  ],
};

describe('CoursePicker Component', () => {
  it('renders branding and course cards', () => {
    const handleSelect = vi.fn();
    const handleRetry = vi.fn();

    render(
      <CoursePicker
        index={mockIndex}
        loading={false}
        error={null}
        onSelectCourse={handleSelect}
        onRetry={handleRetry}
      />
    );

    expect(screen.getByText('PGA Tour Course Viewer')).toBeInTheDocument();
    expect(screen.getByText('Augusta National Golf Club')).toBeInTheDocument();
    expect(screen.getByText('Pebble Beach Golf Links')).toBeInTheDocument();
    expect(screen.getByText('Masters Tournament')).toBeInTheDocument();
    expect(screen.getAllByText('18 Holes').length).toBe(2);
  });

  it('triggers onSelectCourse when card is clicked', () => {
    const handleSelect = vi.fn();
    const handleRetry = vi.fn();

    render(
      <CoursePicker
        index={mockIndex}
        loading={false}
        error={null}
        onSelectCourse={handleSelect}
        onRetry={handleRetry}
      />
    );

    const augustaCard = screen.getByText('Augusta National Golf Club');
    fireEvent.click(augustaCard);

    expect(handleSelect).toHaveBeenCalledWith('augusta_national_golf_club');
  });

  it('renders loading spinner when loading is true', () => {
    render(
      <CoursePicker
        index={null}
        loading={true}
        error={null}
        onSelectCourse={vi.fn()}
        onRetry={vi.fn()}
      />
    );

    expect(screen.getByText(/Loading championship courses/i)).toBeInTheDocument();
  });

  it('renders error alert and retry button when error occurs', () => {
    const handleRetry = vi.fn();

    render(
      <CoursePicker
        index={null}
        loading={false}
        error="Network timeout"
        onSelectCourse={vi.fn()}
        onRetry={handleRetry}
      />
    );

    expect(screen.getByText('Network timeout')).toBeInTheDocument();
    const retryBtn = screen.getByText('Retry Loading');
    fireEvent.click(retryBtn);
    expect(handleRetry).toHaveBeenCalled();
  });
});
