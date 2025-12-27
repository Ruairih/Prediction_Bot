/**
 * Performance Page
 * Charts, metrics, and trade history
 */
import { useSearchParams } from 'react-router-dom';
import { TimeRangeSelector } from '../components/performance/TimeRangeSelector';
import { EquityCurveChart } from '../components/performance/EquityCurveChart';
import { PerformanceKpis } from '../components/performance/PerformanceKpis';
import { WinLossStats } from '../components/performance/WinLossStats';
import { TradeHistoryTable } from '../components/performance/TradeHistoryTable';
import { PnlBreakdown } from '../components/performance/PnlBreakdown';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import { usePerformance } from '../hooks/useDashboardData';
import type { TimeRange } from '../types';

const PAGE_SIZE = 10;

export function Performance() {
  const [searchParams, setSearchParams] = useSearchParams();

  const range = (searchParams.get('range') as TimeRange) || '30d';
  const rawPage = parseInt(searchParams.get('page') || '1', 10);
  const rangeDays = range === '1d' ? 1 : range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : undefined;
  const { data: performanceData, isLoading, error } = usePerformance(rangeDays, 200);

  const stats = performanceData?.stats ?? {
    totalPnl: 0,
    winRate: 0,
    totalTrades: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    maxDrawdownPercent: 0,
    profitFactor: 0,
    avgWin: 0,
    avgLoss: 0,
    bestTrade: 0,
    worstTrade: 0,
  };
  const equityData = performanceData?.equity ?? [];
  const trades = performanceData?.trades ?? [];
  const pnlDaily = performanceData?.pnl.daily ?? [];
  const pnlWeekly = performanceData?.pnl.weekly ?? [];
  const pnlMonthly = performanceData?.pnl.monthly ?? [];

  // Clamp page to valid range
  const totalPages = Math.ceil(trades.length / PAGE_SIZE);
  const page = Math.max(1, Math.min(rawPage, Math.max(1, totalPages)));

  const handleRangeChange = (newRange: TimeRange) => {
    const params = new URLSearchParams(searchParams);
    params.set('range', newRange);
    setSearchParams(params);
  };

  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams);
    params.set('page', String(newPage));
    setSearchParams(params);
  };

  const handleTradeClick = (tradeId: string) => {
    console.log('Trade clicked:', tradeId);
  };

  const paginatedTrades = trades.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Performance</h1>
          <p className="text-text-secondary">Track your trading performance over time</p>
        </div>
        <TimeRangeSelector value={range} onChange={handleRangeChange} />
      </div>

      {isLoading && (
        <div className="text-sm text-text-secondary">Refreshing performance...</div>
      )}

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">
            Unable to load performance data. Ensure the monitoring API is running.
          </p>
        </div>
      )}

      <PerformanceKpis stats={stats} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <EquityCurveChart data={equityData} />
        </div>
        <div>
          <WinLossStats stats={stats} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {paginatedTrades.length === 0 ? (
            <EmptyState
              title="No trades yet"
              description="Your completed trades will appear here"
              icon="📈"
            />
          ) : (
            <>
              <TradeHistoryTable trades={paginatedTrades} onTradeClick={(trade) => handleTradeClick(trade.tradeId)} />
              <div data-testid="trade-pagination">
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={trades.length}
                  onPageChange={handlePageChange}
                />
              </div>
            </>
          )}
        </div>
        <div>
          <PnlBreakdown daily={pnlDaily} weekly={pnlWeekly} monthly={pnlMonthly} />
        </div>
      </div>
    </div>
  );
}
