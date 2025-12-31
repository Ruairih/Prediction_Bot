/**
 * Activity Page
 * Full activity log with filters - fetches real data from API
 */
import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ActivityFilters, ActivityList, ActivityStats, ActivityDetailPanel } from '../components/activity';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import { SkeletonActivity } from '../components/common/Skeleton';
import { useActivity } from '../hooks/useDashboardData';
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
  const { data: eventsData, isLoading, error } = useActivity(200);
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

  // Show skeleton loading state on initial load
  if (isLoading && !eventsData) {
    return <SkeletonActivity />;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Activity</h1>
          <p className="text-text-secondary">Complete activity log and event history</p>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
          <p className="text-red-400">
            Unable to load activity data. Make sure the bot is running on port 9050.
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
        <ActivityDetailPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}
    </div>
  );
}
