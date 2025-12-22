/**
 * Positions Page
 * View and manage open positions - fetches real data from API
 */
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PositionsSummary } from '../components/positions/PositionsSummary';
import { PositionsFilters } from '../components/positions/PositionsFilters';
import { PositionsTable } from '../components/positions/PositionsTable';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import { usePositions, useMetrics } from '../hooks/useDashboardData';
import type { Position, PositionSummary, PositionFilterState } from '../types';

const PAGE_SIZE = 10;

export function Positions() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Parse filters from URL
  const filters: PositionFilterState = {
    status: (searchParams.get('status') as PositionFilterState['status']) || 'all',
    pnl: (searchParams.get('pnl') as PositionFilterState['pnl']) || 'all',
    search: searchParams.get('search') || '',
    sortBy: (searchParams.get('sort') as PositionFilterState['sortBy']) || 'entryTime',
    sortDir: (searchParams.get('dir') as PositionFilterState['sortDir']) || 'desc',
  };

  const rawPage = parseInt(searchParams.get('page') || '1', 10);

  // Fetch real data from API
  const { data: positionsData, isLoading, error } = usePositions();
  const { data: metricsData } = useMetrics();

  // Use API data with fallbacks
  const positions: Position[] = positionsData ?? [];

  // Derive summary from positions data and metrics
  const summary: PositionSummary = useMemo(() => {
    const openPositions = positions.filter((p) => p.status === 'open');
    return {
      openCount: openPositions.length,
      totalExposure: openPositions.reduce((sum, p) => sum + p.entryCost, 0),
      totalUnrealizedPnl: openPositions.reduce((sum, p) => sum + p.unrealizedPnl, 0),
      totalRealizedPnl: metricsData?.totalPnl ?? 0,
    };
  }, [positions, metricsData]);

  // Update URL with filter changes
  const updateFilters = (newFilters: Partial<PositionFilterState>) => {
    const params = new URLSearchParams(searchParams);

    Object.entries(newFilters).forEach(([key, value]) => {
      if (value && value !== 'all' && value !== '') {
        params.set(key === 'sortBy' ? 'sort' : key === 'sortDir' ? 'dir' : key, value);
      } else {
        params.delete(key === 'sortBy' ? 'sort' : key === 'sortDir' ? 'dir' : key);
      }
    });

    // Reset page to 1 when filters change (except for sort changes)
    if (!('sortBy' in newFilters) && !('sortDir' in newFilters)) {
      params.delete('page');
    }

    setSearchParams(params);
  };

  const handleSort = (column: PositionFilterState['sortBy']) => {
    const newDir = filters.sortBy === column && filters.sortDir === 'asc' ? 'desc' : 'asc';
    updateFilters({ sortBy: column, sortDir: newDir });
  };

  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams);
    params.set('page', String(newPage));
    setSearchParams(params);
  };

  // Filter and sort positions
  const filteredPositions = useMemo(() => {
    let result = [...positions];

    // Status filter
    if (filters.status !== 'all') {
      result = result.filter((p) => p.status === filters.status);
    }

    // P&L filter
    if (filters.pnl === 'profitable') {
      result = result.filter((p) => p.unrealizedPnl > 0);
    } else if (filters.pnl === 'losing') {
      result = result.filter((p) => p.unrealizedPnl < 0);
    }

    // Search filter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter((p) =>
        p.question.toLowerCase().includes(searchLower)
      );
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      switch (filters.sortBy) {
        case 'entryTime':
          comparison = new Date(a.entryTime).getTime() - new Date(b.entryTime).getTime();
          break;
        case 'unrealizedPnl':
          comparison = a.unrealizedPnl - b.unrealizedPnl;
          break;
        case 'size':
          comparison = a.size - b.size;
          break;
        case 'pnlPercent':
          comparison = a.pnlPercent - b.pnlPercent;
          break;
      }
      return filters.sortDir === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [positions, filters]);

  // Clamp page to valid range
  const totalPages = Math.ceil(filteredPositions.length / PAGE_SIZE);
  const page = Math.max(1, Math.min(rawPage, Math.max(1, totalPages)));

  // Paginate
  const paginatedPositions = filteredPositions.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE
  );

  const handleClose = (position: Position) => {
    console.log('Close position:', position.positionId);
    // TODO: Implement close modal
  };

  const handleAdjust = (position: Position) => {
    console.log('Adjust position:', position.positionId);
    // TODO: Implement adjust modal
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Positions</h1>
          <p className="text-text-secondary">Manage your open and closed positions</p>
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
            Unable to load positions. Make sure the bot is running on port 5050.
          </p>
        </div>
      )}

      <PositionsSummary summary={summary} />

      <PositionsFilters filters={filters} onFilterChange={updateFilters} />

      {paginatedPositions.length === 0 ? (
        <EmptyState
          title="No positions found"
          description={filters.search ? `No positions match "${filters.search}"` : 'No positions match the current filters'}
          icon="📊"
        />
      ) : (
        <>
          <PositionsTable
            positions={paginatedPositions}
            sortBy={filters.sortBy}
            sortDir={filters.sortDir}
            onSort={handleSort}
            onClose={handleClose}
            onAdjust={handleAdjust}
          />

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={filteredPositions.length}
            onPageChange={handlePageChange}
          />
        </>
      )}
    </div>
  );
}
