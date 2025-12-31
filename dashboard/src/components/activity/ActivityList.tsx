/**
 * Activity List Component
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
  info: 'border-l-text-secondary bg-text-secondary/5',
  success: 'border-l-accent-green bg-accent-green/5',
  warning: 'border-l-accent-yellow bg-accent-yellow/5',
  error: 'border-l-accent-red bg-accent-red/5',
};

export interface ActivityListProps {
  events: ActivityEvent[];
  onEventClick: (event: ActivityEvent) => void;
}

const severityLabels: Record<ActivityEvent['severity'], string> = {
  info: 'Information',
  success: 'Success',
  warning: 'Warning',
  error: 'Error',
};

export function ActivityList({ events, onEventClick }: ActivityListProps) {
  return (
    <div
      data-testid="activity-list"
      className="bg-bg-secondary rounded-lg border border-border overflow-hidden"
      role="log"
      aria-live="polite"
      aria-label="Activity events list"
    >
      <div className="divide-y divide-border">
        {events.map((event) => (
          <button
            key={event.id}
            data-testid="activity-list-item"
            data-severity={event.severity}
            onClick={() => onEventClick(event)}
            aria-label={`${severityLabels[event.severity]}: ${event.type.replace(/_/g, ' ')} - ${event.summary}`}
            className={clsx(
              'w-full flex items-start gap-4 p-4 text-left border-l-4 transition-colors',
              'hover:bg-bg-tertiary/50 focus:outline-none focus:ring-2 focus:ring-accent-blue focus:ring-inset',
              severityColors[event.severity]
            )}
          >
            <span className="text-xl" aria-hidden="true">
              {typeIcons[event.type]}
            </span>

            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs font-medium uppercase text-text-secondary">
                  {event.type.replace(/_/g, ' ')}
                </span>
                <span className="text-xs text-text-secondary">
                  {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                </span>
              </div>
              <div className="text-sm text-text-primary mt-1 truncate">
                {event.summary}
              </div>
              {/* Screen reader only severity indicator */}
              <span className="sr-only">Severity: {severityLabels[event.severity]}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
