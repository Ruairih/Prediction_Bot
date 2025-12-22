/**
 * Unit Tests for ActivityStream Component
 *
 * Written FIRST (TDD) - defines expected behavior before implementation.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ActivityStream } from './ActivityStream';
import type { ActivityEvent } from '../../types';

const mockEvents: ActivityEvent[] = [
  {
    id: '1',
    type: 'order_filled',
    timestamp: new Date().toISOString(),
    summary: 'BUY 2 @ $0.95',
    details: { tokenId: 'tok_123', price: 0.95 },
    severity: 'success',
  },
  {
    id: '2',
    type: 'signal',
    timestamp: new Date(Date.now() - 60000).toISOString(),
    summary: 'Signal rejected: size filter',
    details: { reason: 'Size 45 < 50' },
    severity: 'warning',
  },
  {
    id: '3',
    type: 'error',
    timestamp: new Date(Date.now() - 120000).toISOString(),
    summary: 'WebSocket reconnected',
    details: {},
    severity: 'error',
  },
];

describe('ActivityStream', () => {
  it('renders activity items', () => {
    render(<ActivityStream events={mockEvents} />);

    expect(screen.getByText('BUY 2 @ $0.95')).toBeInTheDocument();
    expect(screen.getByText(/signal rejected/i)).toBeInTheDocument();
  });

  it('displays timestamps in relative format', () => {
    render(<ActivityStream events={mockEvents} />);

    // Should show relative times
    expect(screen.getAllByText(/ago|just now/i).length).toBeGreaterThan(0);
  });

  it('applies severity-based styling', () => {
    render(<ActivityStream events={mockEvents} />);

    const successItem = screen.getByText('BUY 2 @ $0.95').closest('[data-testid="activity-item"]');
    expect(successItem).toHaveAttribute('data-severity', 'success');
  });

  it('shows empty state when no events', () => {
    render(<ActivityStream events={[]} />);

    expect(screen.getByText(/no activity/i)).toBeInTheDocument();
  });

  it('calls onEventClick when event clicked', () => {
    const onEventClick = vi.fn();
    render(<ActivityStream events={mockEvents} onEventClick={onEventClick} />);

    fireEvent.click(screen.getByText('BUY 2 @ $0.95'));
    expect(onEventClick).toHaveBeenCalledWith(mockEvents[0]);
  });

  it('limits displayed events to maxEvents prop', () => {
    const manyEvents = Array.from({ length: 20 }, (_, i) => ({
      ...mockEvents[0],
      id: String(i),
      summary: `Event ${i}`,
    }));

    render(<ActivityStream events={manyEvents} maxEvents={5} />);

    // Should only show 5 events
    const items = screen.getAllByTestId('activity-item');
    expect(items.length).toBe(5);
  });

  it('shows type icon for each event', () => {
    render(<ActivityStream events={mockEvents} />);

    // Each event should have an icon
    const icons = screen.getAllByTestId('activity-icon');
    expect(icons.length).toBe(mockEvents.length);
  });

  it('shows newest event first when events are updated', async () => {
    const { rerender } = render(<ActivityStream events={mockEvents} />);

    const newEvent: ActivityEvent = {
      id: 'new',
      type: 'order_filled',
      timestamp: new Date().toISOString(),
      summary: 'NEW EVENT',
      details: {},
      severity: 'success',
    };

    rerender(<ActivityStream events={[newEvent, ...mockEvents]} />);

    // First item should be the new event
    const items = screen.getAllByTestId('activity-item');
    expect(items[0]).toHaveTextContent('NEW EVENT');
  });
});
