/**
 * Activity Page
 * Full activity log with filters - fetches real data from API
 */
import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ActivityFilters } from '../components/activity/ActivityFilters';
import { ActivityList } from '../components/activity/ActivityList';
import { ActivityStats } from '../components/activity/ActivityStats';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import { useTriggers } from '../hooks/useDashboardData';
import type { ActivityEvent, ActivityFilterState, ActivityStats as ActivityStatsType } from '../types';

const PAGE_SIZE = 20;

export function Activity() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: ActivityFilterState = {
    types: searchParams.get('type')?.split(',').filter(Boolean) as ActivityFilterState['types'] || [],
    severities: searchParams.get('severity')?.split(',').filter(Boolean) as ActivityFilterState['severities'] || [],
    startDate: searchParams.get('startDate') || null,
    endDate: searchParams.get('endDate') || null,
    search: searchParams.get('search') || '',
  };

  const rawPage = parseInt(searchParams.get('page') || '1', 10);

  // Fetch real data from API (get more events for better filtering)
  const { data: eventsData, isLoading, error } = useTriggers(100);
  const events: ActivityEvent[] = eventsData ?? [];
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);

  // Derive stats from events data
  const stats: ActivityStatsType = useMemo(() => {
    const byType: Record<string, number> = {};
    const bySeverity: Record<string, number> = {};

    events.forEach((event) => {
      byType[event.type] = (byType[event.type] || 0) + 1;
      bySeverity[event.severity] = (bySeverity[event.severity] || 0) + 1;
    });

    return {
      total: events.length,
      byType: byType as ActivityStatsType['byType'],
      bySeverity: bySeverity as ActivityStatsType['bySeverity'],
    };
  }, [events]);

  const updateFilters = (newFilters: Partial<ActivityFilterState>) => {
    const params = new URLSearchParams(searchParams);

    Object.entries(newFilters).forEach(([key, value]) => {
      if (value && (Array.isArray(value) ? value.length > 0 : value !== '')) {
        params.set(key, Array.isArray(value) ? value.join(',') : value);
      } else {
        params.delete(key);
      }
    });

    // Reset page to 1 when filters change
    params.delete('page');

    setSearchParams(params);
  };

  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams);
    params.set('page', String(newPage));
    setSearchParams(params);
  };

  // Filter events
  const filteredEvents = useMemo(() => {
    let result = [...events];

    if (filters.types.length > 0) {
      result = result.filter((e) => filters.types.includes(e.type));
    }

    if (filters.severities.length > 0) {
      result = result.filter((e) => filters.severities.includes(e.severity));
    }

    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter((e) =>
        e.summary.toLowerCase().includes(searchLower)
      );
    }

    if (filters.startDate) {
      const start = new Date(filters.startDate);
      result = result.filter((e) => new Date(e.timestamp) >= start);
    }

    if (filters.endDate) {
      const end = new Date(filters.endDate);
      end.setHours(23, 59, 59, 999);
      result = result.filter((e) => new Date(e.timestamp) <= end);
    }

    return result;
  }, [events, filters]);

  // Clamp page to valid range
  const totalPages = Math.ceil(filteredEvents.length / PAGE_SIZE);
  const page = Math.max(1, Math.min(rawPage, Math.max(1, totalPages)));

  const paginatedEvents = filteredEvents.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Activity</h1>
          <p className="text-text-secondary">Complete activity log and event history</p>
        </div>

        {/* Loading indicator */}
        {isLoading && (
          <span className="text-text-secondary text-sm">Loading...</span>
        )}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
          <p className="text-red-400">
            Unable to load activity data. Make sure the bot is running on port 5050.
          </p>
        </div>
      )}

      <ActivityStats stats={stats} />

      <ActivityFilters filters={filters} onFilterChange={updateFilters} />

      {paginatedEvents.length === 0 ? (
        <EmptyState
          title="No activity found"
          description="No events match the current filters"
          icon="📜"
        />
      ) : (
        <>
          <ActivityList events={paginatedEvents} onEventClick={setSelectedEvent} />

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={filteredEvents.length}
            onPageChange={handlePageChange}
          />
        </>
      )}

      {/* Activity Details Drawer */}
      {selectedEvent && (
        <div
          data-testid="activity-drawer"
          className="fixed inset-y-0 right-0 w-96 bg-bg-secondary border-l border-border shadow-xl z-50"
        >
          <div className="flex items-center justify-between p-4 border-b border-border">
            <h3 className="text-lg font-semibold text-text-primary">Event Details</h3>
            <button
              onClick={() => setSelectedEvent(null)}
              className="text-text-secondary hover:text-text-primary"
            >
              ✕
            </button>
          </div>
          <div className="p-4 space-y-4">
            <div>
              <span className="text-xs text-text-secondary uppercase">Type</span>
              <p className="text-text-primary">{selectedEvent.type.replace(/_/g, ' ')}</p>
            </div>
            <div>
              <span className="text-xs text-text-secondary uppercase">Timestamp</span>
              <p className="text-text-primary">{new Date(selectedEvent.timestamp).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-xs text-text-secondary uppercase">Summary</span>
              <p className="text-text-primary">{selectedEvent.summary}</p>
            </div>
            <div>
              <span className="text-xs text-text-secondary uppercase">Details</span>
              <pre className="mt-2 p-3 bg-bg-tertiary rounded text-xs overflow-auto text-text-primary">
                {JSON.stringify(selectedEvent.details, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
