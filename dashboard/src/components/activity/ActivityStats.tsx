/**
 * Activity Stats Component
 */
import type { ActivityStats as ActivityStatsType } from '../../types';

export interface ActivityStatsProps {
  stats: ActivityStatsType;
}

export function ActivityStats({ stats }: ActivityStatsProps) {
  return (
    <div
      data-testid="activity-stats"
      className="flex flex-wrap gap-4 mb-6"
    >
      <div className="bg-bg-secondary rounded-lg px-4 py-2 border border-border">
        <span className="text-text-secondary text-sm">Total Events: </span>
        <span className="text-text-primary font-semibold">{stats.total}</span>
      </div>

      <div className="bg-bg-secondary rounded-lg px-4 py-2 border border-border">
        <span className="text-text-secondary text-sm">Orders: </span>
        <span className="text-text-primary font-semibold">
          {(stats.byType.order_submitted || 0) + (stats.byType.order_filled || 0)}
        </span>
      </div>

      <div className="bg-bg-secondary rounded-lg px-4 py-2 border border-border">
        <span className="text-text-secondary text-sm">Signals: </span>
        <span className="text-text-primary font-semibold">{stats.byType.signal || 0}</span>
      </div>

      <div className="bg-bg-secondary rounded-lg px-4 py-2 border border-border">
        <span className="text-text-secondary text-sm">Errors: </span>
        <span className="text-accent-red font-semibold">{stats.bySeverity.error || 0}</span>
      </div>
    </div>
  );
}
