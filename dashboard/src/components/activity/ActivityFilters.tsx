/**
 * Activity Filters Component
 */
import type { ActivityFilterState } from '../../types';

// Available filter options - will be used when dropdown is implemented
// const activityTypes: ActivityType[] = ['price_update', 'signal', 'order_submitted', ...];
// const severities = ['info', 'success', 'warning', 'error'] as const;

export interface ActivityFiltersProps {
  filters: ActivityFilterState;
  onFilterChange: (filters: Partial<ActivityFilterState>) => void;
}

export function ActivityFilters({ filters, onFilterChange }: ActivityFiltersProps) {
  return (
    <div
      data-testid="activity-filters"
      className="flex flex-wrap items-center gap-4 mb-4"
    >
      {/* Type Filter Dropdown */}
      <div className="relative">
        <button
          type="button"
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary hover:bg-bg-tertiary/80 transition-colors"
        >
          Type ({filters.types.length || 'All'})
        </button>
        {/* TODO: Implement dropdown with checkboxes */}
      </div>

      {/* Severity Filter Dropdown */}
      <div className="relative">
        <button
          type="button"
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary hover:bg-bg-tertiary/80 transition-colors"
        >
          Severity ({filters.severities.length || 'All'})
        </button>
        {/* TODO: Implement dropdown with checkboxes */}
      </div>

      {/* Date Range Picker */}
      <div data-testid="date-range-picker" className="flex items-center gap-2">
        <input
          type="date"
          value={filters.startDate || ''}
          onChange={(e) => onFilterChange({ startDate: e.target.value || null })}
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        />
        <span className="text-text-secondary">to</span>
        <input
          type="date"
          value={filters.endDate || ''}
          onChange={(e) => onFilterChange({ endDate: e.target.value || null })}
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        />
      </div>

      {/* Search */}
      <div className="flex-1 min-w-[200px]">
        <input
          type="search"
          role="searchbox"
          placeholder="Search activity..."
          value={filters.search}
          onChange={(e) => onFilterChange({ search: e.target.value })}
          className="w-full bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        />
      </div>

      {/* Export Button */}
      <button
        className="bg-accent-blue text-white px-4 py-1.5 rounded-lg text-sm hover:bg-accent-blue/80 transition-colors"
      >
        Export CSV
      </button>
    </div>
  );
}
