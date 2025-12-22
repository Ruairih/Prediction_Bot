/**
 * Performance Page
 * Charts, metrics, and trade history
 */
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { TimeRangeSelector } from '../components/performance/TimeRangeSelector';
import { EquityCurveChart } from '../components/performance/EquityCurveChart';
import { PerformanceKpis } from '../components/performance/PerformanceKpis';
import { WinLossStats } from '../components/performance/WinLossStats';
import { TradeHistoryTable } from '../components/performance/TradeHistoryTable';
import { PnlBreakdown } from '../components/performance/PnlBreakdown';
import { Pagination } from '../components/common/Pagination';
import { EmptyState } from '../components/common/EmptyState';
import type { TimeRange, EquityPoint, PerformanceStats, Trade, PnlBucket } from '../types';

// Mock data
const generateEquityData = (): EquityPoint[] => {
  const data: EquityPoint[] = [];
  let equity = 400;
  const now = Date.now();

  for (let i = 30; i >= 0; i--) {
    equity += Math.random() * 10 - 3;
    data.push({
      timestamp: new Date(now - i * 86400000).toISOString(),
      equity: Math.max(equity, 350),
    });
  }

  return data;
};

const mockEquityData = generateEquityData();

const mockStats: PerformanceStats = {
  totalPnl: 47.82,
  winRate: 0.985,
  totalTrades: 68,
  sharpeRatio: 2.34,
  maxDrawdown: 12.50,
  maxDrawdownPercent: 3.2,
  profitFactor: 4.8,
  avgWin: 2.15,
  avgLoss: 1.80,
  bestTrade: 8.50,
  worstTrade: 5.20,
};

const mockTrades: Trade[] = [
  {
    tradeId: '1',
    positionId: 'pos1',
    tokenId: 'token1',
    question: 'Will Bitcoin reach $100k by end of 2024?',
    side: 'BUY',
    size: 50,
    entryPrice: 0.45,
    exitPrice: 0.52,
    pnl: 3.50,
    pnlPercent: 15.56,
    openedAt: new Date(Date.now() - 86400000 * 5).toISOString(),
    closedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
    holdingPeriod: 3,
    category: 'Crypto',
  },
  {
    tradeId: '2',
    positionId: 'pos2',
    tokenId: 'token2',
    question: 'Will Fed cut rates in March?',
    side: 'BUY',
    size: 100,
    entryPrice: 0.65,
    exitPrice: 0.71,
    pnl: 6.00,
    pnlPercent: 9.23,
    openedAt: new Date(Date.now() - 86400000 * 10).toISOString(),
    closedAt: new Date(Date.now() - 86400000 * 7).toISOString(),
    holdingPeriod: 3,
    category: 'Economics',
  },
  {
    tradeId: '3',
    positionId: 'pos3',
    tokenId: 'token3',
    question: 'Will ETH merge happen on time?',
    side: 'SELL',
    size: 75,
    entryPrice: 0.80,
    exitPrice: 0.72,
    pnl: -6.00,
    pnlPercent: -10.0,
    openedAt: new Date(Date.now() - 86400000 * 15).toISOString(),
    closedAt: new Date(Date.now() - 86400000 * 12).toISOString(),
    holdingPeriod: 3,
    category: 'Crypto',
  },
];

const mockDailyPnl: PnlBucket[] = [
  { period: 'Today', pnl: 3.20, trades: 2, wins: 2, losses: 0 },
  { period: 'Yesterday', pnl: -1.50, trades: 1, wins: 0, losses: 1 },
  { period: 'Dec 19', pnl: 5.80, trades: 3, wins: 3, losses: 0 },
  { period: 'Dec 18', pnl: 2.10, trades: 2, wins: 2, losses: 0 },
  { period: 'Dec 17', pnl: 4.50, trades: 2, wins: 2, losses: 0 },
];

const mockWeeklyPnl: PnlBucket[] = [
  { period: 'This Week', pnl: 12.50, trades: 8, wins: 7, losses: 1 },
  { period: 'Last Week', pnl: 18.30, trades: 12, wins: 11, losses: 1 },
  { period: 'Dec 9-15', pnl: 9.20, trades: 6, wins: 6, losses: 0 },
];

const mockMonthlyPnl: PnlBucket[] = [
  { period: 'December', pnl: 47.82, trades: 68, wins: 67, losses: 1 },
  { period: 'November', pnl: 32.50, trades: 45, wins: 43, losses: 2 },
];

const PAGE_SIZE = 10;

export function Performance() {
  const [searchParams, setSearchParams] = useSearchParams();

  const range = (searchParams.get('range') as TimeRange) || '30d';
  const rawPage = parseInt(searchParams.get('page') || '1', 10);

  const [equityData] = useState<EquityPoint[]>(mockEquityData);
  const [stats] = useState<PerformanceStats>(mockStats);
  const [trades] = useState<Trade[]>(mockTrades);

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

  const handleTradeClick = (trade: Trade) => {
    console.log('Trade clicked:', trade.tradeId);
    // TODO: Implement trade details drawer
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
              <TradeHistoryTable trades={paginatedTrades} onTradeClick={handleTradeClick} />
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
          <PnlBreakdown daily={mockDailyPnl} weekly={mockWeeklyPnl} monthly={mockMonthlyPnl} />
        </div>
      </div>
    </div>
  );
}
