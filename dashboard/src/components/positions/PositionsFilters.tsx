/**
 * Positions Filters Component
 */
import type { PositionFilterState } from '../../types';

export interface PositionsFiltersProps {
  filters: PositionFilterState;
  onFilterChange: (filters: Partial<PositionFilterState>) => void;
}

export function PositionsFilters({ filters, onFilterChange }: PositionsFiltersProps) {
  return (
    <div
      data-testid="positions-filters"
      className="flex flex-wrap items-center gap-4 mb-4"
    >
      <div className="flex items-center gap-2">
        <label htmlFor="status-filter" className="text-sm text-text-secondary">
          Status:
        </label>
        <select
          id="status-filter"
          aria-label="Status filter"
          value={filters.status}
          onChange={(e) => onFilterChange({ status: e.target.value as PositionFilterState['status'] })}
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        >
          <option value="all">All</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="pnl-filter" className="text-sm text-text-secondary">
          P&L:
        </label>
        <select
          id="pnl-filter"
          aria-label="P&L filter"
          value={filters.pnl}
          onChange={(e) => onFilterChange({ pnl: e.target.value as PositionFilterState['pnl'] })}
          className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        >
          <option value="all">All</option>
          <option value="profitable">Profitable</option>
          <option value="losing">Losing</option>
        </select>
      </div>

      <div className="flex-1 min-w-[200px]">
        <input
          type="search"
          role="searchbox"
          placeholder="Search positions..."
          value={filters.search}
          onChange={(e) => onFilterChange({ search: e.target.value })}
          className="w-full bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-blue"
        />
      </div>
    </div>
  );
}
