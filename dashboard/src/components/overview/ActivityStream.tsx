/**
 * Activity Stream Component
 *
 * Displays a real-time feed of trading activity.
 */
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import type { ActivityEvent, ActivityType } from '../../types';

const typeIcons: Record<ActivityType, string> = {
  price_update: '📊',
  signal: '🎯',
  order_submitted: '📤',
  order_filled: '✅',
  order_cancelled: '❌',
  position_opened: '📈',
  position_closed: '📉',
  bot_state_change: '🤖',
  alert: '🔔',
  error: '⚠️',
};

const severityColors = {
  info: 'border-l-text-secondary',
  success: 'border-l-accent-green',
  warning: 'border-l-accent-yellow',
  error: 'border-l-accent-red',
};

export interface ActivityStreamProps {
  events: ActivityEvent[];
  maxEvents?: number;
  onEventClick?: (event: ActivityEvent) => void;
  isLoading?: boolean;
}

export function ActivityStream({
  events,
  maxEvents = 10,
  onEventClick,
  isLoading = false,
}: ActivityStreamProps) {
  const displayedEvents = events.slice(0, maxEvents);

  if (events.length === 0) {
    return (
      <div
        data-testid="activity-stream"
        className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
              Activity
            </div>
            <h3 className="text-lg font-semibold text-text-primary">
              Live Tape
            </h3>
          </div>
          <span className="text-xs text-text-secondary">No recent events</span>
        </div>
        <div className="text-text-secondary text-center py-8">
          {isLoading ? 'Loading activity...' : 'No activity yet'}
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="activity-stream"
      className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm"
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Activity
          </div>
          <h3 className="text-lg font-semibold text-text-primary">
            Live Tape
          </h3>
        </div>
        <span className="text-xs text-text-secondary">{displayedEvents.length} events</span>
      </div>

      <div className="space-y-2 max-h-80 overflow-y-auto" role="log" aria-live="polite" aria-label="Trading activity feed">
        {displayedEvents.map((event) => (
          <button
            key={event.id}
            type="button"
            data-testid="activity-item"
            data-severity={event.severity}
            onClick={() => onEventClick?.(event)}
            className={clsx(
              'flex items-start gap-3 p-3 rounded-xl border-l-2 w-full text-left border border-border/60',
              'hover:bg-bg-tertiary transition-colors focus:outline-none focus:ring-2 focus:ring-accent-blue',
              onEventClick ? 'cursor-pointer' : 'cursor-default',
              severityColors[event.severity]
            )}
            aria-label={`${event.type}: ${event.summary}`}
          >
            <span data-testid="activity-icon" className="text-lg" aria-hidden="true">
              {typeIcons[event.type]}
            </span>

            <div className="flex-1 min-w-0">
              <div className="text-text-primary text-sm truncate">
                {event.summary}
              </div>
              <div className="text-text-secondary text-xs">
                {formatDistanceToNow(new Date(event.timestamp), {
                  addSuffix: true,
                })}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
