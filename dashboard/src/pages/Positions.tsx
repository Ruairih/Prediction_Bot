/**
 * Positions Page
 * View and manage open positions - fetches real data from API
 */
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { PositionsSummary } from '../components/positions/PositionsSummary';
import { PositionsFilters } from '../components/positions/PositionsFilters';
import { PositionsTable } from '../components/positions/PositionsTable';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import { usePositions, useMetrics, useOrders } from '../hooks/useDashboardData';
import { cancelAllOrders, flattenPositions, closePosition } from '../api/dashboard';
import type { Position, PositionSummary, PositionFilterState, Order } from '../types';

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
  const { data: ordersData, isLoading: ordersLoading } = useOrders(200);

  // Use API data with fallbacks
  const positions: Position[] = positionsData ?? [];
  const orders: Order[] = ordersData ?? [];

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

  const handleClose = async (position: Position) => {
    if (!window.confirm(`Close position ${position.positionId}?`)) {
      return;
    }
    try {
      const result = await closePosition(
        position.positionId,
        position.currentPrice,
        'portfolio_close',
        position.tokenId
      );
      if (!result?.success) {
        window.alert(result?.error ?? 'Close failed.');
      }
    } catch (error) {
      window.alert(`Close failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleAdjust = async (position: Position) => {
    const input = window.prompt(`Limit exit price for ${position.question}`, '');
    if (input === null) {
      return;
    }
    const price = Number(input);
    if (!Number.isFinite(price) || price <= 0) {
      window.alert('Enter a valid limit price.');
      return;
    }
    try {
      const result = await closePosition(position.positionId, price, 'limit_exit', position.tokenId);
      if (!result?.success) {
        window.alert(result?.error ?? 'Exit limit failed.');
      }
    } catch (error) {
      window.alert(`Exit limit failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const recentOrders = useMemo(() => {
    const sorted = [...orders];
    sorted.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    return sorted.slice(0, 20);
  }, [orders]);

  return (
    <div className="px-6 py-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Portfolio
          </div>
          <h1 className="text-3xl font-semibold text-text-primary">Positions & Orders</h1>
          <p className="text-text-secondary">Manage live exposure and exit controls.</p>
        </div>

        <div className="flex items-center gap-3 text-sm">
          <button
            className="px-4 py-2 rounded-full border border-border bg-bg-secondary shadow-sm hover:border-accent-blue hover:text-accent-blue transition-colors"
            onClick={() => window.location.reload()}
          >
            Sync
          </button>
          <button
            className="px-4 py-2 rounded-full border border-border bg-bg-secondary shadow-sm hover:border-accent-yellow hover:text-accent-yellow transition-colors"
            onClick={() => cancelAllOrders()}
          >
            Cancel All
          </button>
          <button
            className="px-4 py-2 rounded-full border border-border bg-bg-secondary shadow-sm hover:border-accent-red hover:text-accent-red transition-colors"
            onClick={() => flattenPositions('portfolio')}
          >
            Flatten
          </button>
          {(isLoading || ordersLoading) && (
            <span className="text-text-secondary text-xs">Loading...</span>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">
            Unable to load positions. Make sure the bot is running on port 9050.
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

          <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm overflow-hidden mt-6">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="text-sm text-text-secondary">
                Order Blotter
              </div>
              <div className="text-xs text-text-secondary">
                {recentOrders.length} recent orders
              </div>
            </div>
            {recentOrders.length === 0 ? (
              <div className="px-4 py-6 text-sm text-text-secondary">
                No orders recorded yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-bg-tertiary text-text-secondary text-xs uppercase tracking-widest">
                    <tr>
                      <th className="px-4 py-3 text-left">Order</th>
                      <th className="px-4 py-3 text-right">Side</th>
                      <th className="px-4 py-3 text-right">Price</th>
                      <th className="px-4 py-3 text-right">Size</th>
                      <th className="px-4 py-3 text-right">Filled</th>
                      <th className="px-4 py-3 text-right">Status</th>
                      <th className="px-4 py-3 text-right">Slippage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {recentOrders.map((order) => (
                      <tr key={order.orderId} className="hover:bg-bg-tertiary/60">
                        <td className="px-4 py-3">
                          <div className="text-text-primary">{order.question}</div>
                          <div className="text-xs text-text-secondary">
                            {formatDistanceToNow(new Date(order.createdAt), { addSuffix: true })}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right text-text-primary">
                          {order.side}
                        </td>
                        <td className="px-4 py-3 text-right text-text-primary">
                          {order.price.toFixed(3)}
                        </td>
                        <td className="px-4 py-3 text-right text-text-primary">
                          {order.size.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right text-text-secondary">
                          {order.filledSize.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right text-text-secondary">
                          {order.status}
                        </td>
                        <td className="px-4 py-3 text-right text-text-secondary">
                          {order.slippage !== undefined ? `${order.slippage.toFixed(1)} bps` : '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={filteredPositions.length}
            onPageChange={handlePageChange}
          />
        </>
      )}

      <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-text-primary">Order Blotter</h3>
          <span className="text-xs text-text-secondary">{orders.length} orders</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bg-tertiary text-text-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="px-4 py-3 text-left">Token</th>
                <th className="px-4 py-3 text-right">Side</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Size</th>
                <th className="px-4 py-3 text-right">Filled</th>
                <th className="px-4 py-3 text-right">Status</th>
                <th className="px-4 py-3 text-right">Submitted</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {orders.slice(0, 20).map((order) => (
                <tr key={order.orderId} className="hover:bg-bg-tertiary/60">
                  <td className="px-4 py-3 text-text-primary">{order.tokenId.slice(0, 8)}...</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{order.side}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{order.price.toFixed(3)}</td>
                  <td className="px-4 py-3 text-right text-text-primary">{order.size.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{order.filledSize.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">{order.status}</td>
                  <td className="px-4 py-3 text-right text-text-secondary">
                    {new Date(order.createdAt).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-text-secondary">
                    No orders yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
