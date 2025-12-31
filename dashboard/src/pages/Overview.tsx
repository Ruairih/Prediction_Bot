/**
 * Overview Page - Mission Control
 *
 * Primary operator surface with KPIs, activity, and system pulse.
 */
import { useMemo, useState } from 'react';
import { formatDistanceToNowStrict } from 'date-fns';
import { KpiTile } from '../components/overview/KpiTile';
import { BotStatus } from '../components/overview/BotStatus';
import { ActivityStream } from '../components/overview/ActivityStream';
import { EquityCurveChart } from '../components/performance/EquityCurveChart';
import { SkeletonOverview } from '../components/common/Skeleton';
import { useBotStatus, useMetrics, useActivity, usePositions, usePerformance } from '../hooks/useDashboardData';
import { pauseTrading, resumeTrading, killTrading } from '../api/dashboard';
import type { BotStatus as BotStatusType, DashboardMetrics, ActivityEvent, Position } from '../types';

// Fallback values when API is unavailable
const fallbackStatus: BotStatusType = {
  mode: 'stopped',
  status: 'unhealthy',
  lastHeartbeat: new Date().toISOString(),
  lastTradeTime: null,
  errorRate: 0,
  websocketConnected: false,
  version: '1.0.0',
};

const fallbackMetrics: DashboardMetrics = {
  totalPnl: 0,
  todayPnl: 0,
  winRate: 0,
  totalTrades: 0,
  winningTrades: 0,
  losingTrades: 0,
  openPositions: 0,
  availableBalance: 0,
  capitalDeployed: 0,
  calculatedAt: new Date().toISOString(),
};

export function Overview() {
  // Fetch real data from API
  const { data: statusData, isLoading: statusLoading, error: statusError } = useBotStatus();
  const { data: metricsData, isLoading: metricsLoading, error: metricsError } = useMetrics();
  const { data: activityData, isLoading: activityLoading } = useActivity(20);
  const { data: positionsData } = usePositions();
  const { data: performanceData } = usePerformance(30);

  // Use API data or fallbacks
  const status = statusData ?? fallbackStatus;
  const metrics = metricsData ?? fallbackMetrics;
  const activity = activityData ?? [];
  const positions = positionsData ?? [];

  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);

  const handlePause = async () => {
    if (status.mode === 'paused') {
      await resumeTrading();
      return;
    }
    await pauseTrading('mission_control');
  };

  const handleStop = async () => {
    if (!window.confirm('Stop the bot now?')) {
      return;
    }
    await killTrading('mission_control');
  };

  const pnlTrend = metrics.totalPnl >= 0 ? 'up' : 'down';
  const todayTrend = metrics.todayPnl >= 0 ? 'up' : 'down';

  const totalAssets = metrics.availableBalance + metrics.capitalDeployed;
  const exposurePercent = totalAssets > 0 ? (metrics.capitalDeployed / totalAssets) * 100 : 0;

  const topPositions = useMemo(() => {
    const sortable = [...positions];
    sortable.sort((a, b) => b.pnlPercent - a.pnlPercent);
    return sortable.slice(0, 4);
  }, [positions]);

  // Show connection status
  const isConnected = !statusError && !metricsError;
  const isLoading = statusLoading || metricsLoading;

  // Show skeleton loading state on initial load
  if (isLoading && !statusData && !metricsData) {
    return <SkeletonOverview />;
  }

  return (
    <div className="px-6 py-6 space-y-6">
      {/* Page Title */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Mission Control
          </div>
          <h1 className="text-3xl font-semibold text-text-primary">
            Trading Command Desk
          </h1>
          <p className="text-text-secondary">
            Real-time pulse on positions, signals, and system health.
          </p>
        </div>

        {/* Connection Status */}
        <div className="flex items-center gap-3 rounded-full border border-border bg-bg-secondary px-4 py-2 text-sm shadow-sm">
          {isLoading && (
            <span className="text-text-secondary text-xs">Syncing data...</span>
          )}
          <div
            className={`w-2 h-2 rounded-full ${isConnected ? 'bg-accent-green' : 'bg-accent-red'}`}
            aria-hidden="true"
          />
          <span className="text-text-secondary">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Error Banner */}
      {(statusError || metricsError) && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">
            Unable to connect to monitoring API. Make sure the bot is running on port 9050.
          </p>
          <p className="text-accent-red/70 text-sm mt-1">
            Run: <code className="bg-bg-tertiary px-1 rounded">python -m polymarket_bot.main --mode all</code>
          </p>
        </div>
      )}

      {/* KPI Tiles */}
      <div data-testid="kpi-container" className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <KpiTile
          testId="kpi-total-pnl"
          label="Total P&L"
          value={`$${metrics.totalPnl.toFixed(2)}`}
          change={metrics.totalPnl !== 0 ? `${metrics.totalPnl > 0 ? '+' : ''}${((metrics.totalPnl / Math.max(metrics.capitalDeployed, 1)) * 100).toFixed(1)}%` : '—'}
          trend={pnlTrend}
        />
        <KpiTile
          testId="kpi-today-pnl"
          label="Today's P&L"
          value={`$${metrics.todayPnl.toFixed(2)}`}
          change={metrics.todayPnl !== 0 ? `${metrics.todayPnl > 0 ? '+' : ''}${metrics.todayPnl.toFixed(1)}%` : '—'}
          trend={todayTrend}
        />
        <KpiTile
          testId="kpi-win-rate"
          label="Win Rate"
          value={`${(metrics.winRate * 100).toFixed(1)}%`}
          change={`${metrics.winningTrades}/${metrics.totalTrades}`}
        />
        <KpiTile
          testId="kpi-positions"
          label="Open Positions"
          value={String(metrics.openPositions)}
          change={`$${metrics.capitalDeployed.toFixed(2)} deployed`}
        />
        <KpiTile
          testId="kpi-balance"
          label="Available"
          value={`$${metrics.availableBalance.toFixed(2)}`}
          change="Reserve balance"
        />
        <KpiTile
          testId="kpi-exposure"
          label="Exposure"
          value={`${exposurePercent.toFixed(1)}%`}
          change={`$${metrics.capitalDeployed.toFixed(2)}`}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity Stream - Takes 2 columns on large screens */}
        <div className="lg:col-span-2 space-y-6">
          <ActivityStream
            events={activity}
            maxEvents={10}
            onEventClick={setSelectedEvent}
            isLoading={activityLoading}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
              <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
                Exposure
              </div>
              <h3 className="text-lg font-semibold text-text-primary mb-3">
                Risk Snapshot
              </h3>
              <div className="flex items-center justify-between text-sm text-text-secondary">
                <span>Deployed</span>
                <span className="text-text-primary">
                  ${metrics.capitalDeployed.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm text-text-secondary mt-2">
                <span>Reserve</span>
                <span className="text-text-primary">
                  ${metrics.availableBalance.toFixed(2)}
                </span>
              </div>
              <div className="mt-4">
                <div className="h-2 rounded-full bg-bg-tertiary">
                  <div
                    className="h-full rounded-full bg-accent-blue"
                    style={{ width: `${Math.min(exposurePercent, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-text-secondary mt-2">
                  <span>0%</span>
                  <span>{exposurePercent.toFixed(1)}%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>

            <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
              <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
                Positions
              </div>
              <h3 className="text-lg font-semibold text-text-primary mb-3">
                Highlights
              </h3>
              {topPositions.length === 0 ? (
                <div className="text-text-secondary text-sm">No open positions yet.</div>
              ) : (
                <div className="space-y-3">
                  {topPositions.map((position: Position) => (
                    <div key={position.positionId} className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm text-text-primary truncate">
                          {position.question}
                        </div>
                        <div className="text-xs text-text-secondary">
                          Opened {formatDistanceToNowStrict(new Date(position.entryTime))} ago
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={position.unrealizedPnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                          {position.unrealizedPnl >= 0 ? '+' : '-'}${Math.abs(position.unrealizedPnl).toFixed(2)}
                        </div>
                        <div className="text-xs text-text-secondary">
                          {position.pnlPercent.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Bot Status */}
        <div className="space-y-6">
          <BotStatus
            status={status}
            onPause={handlePause}
            onStop={handleStop}
          />

          <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
            <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
              Signals
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-3">
              Decision Pulse
            </h3>
            <div className="space-y-2 text-sm text-text-secondary">
              <div className="flex items-center justify-between">
                <span>Win rate</span>
                <span className="text-text-primary">{(metrics.winRate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Triggers evaluated</span>
                <span className="text-text-primary">{metrics.totalTrades}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Live mode</span>
                <span className="text-text-primary">{status.mode}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <div data-testid="equity-curve" className="rounded-2xl">
        <EquityCurveChart data={performanceData?.equity ?? []} />
      </div>

      {/* Activity Details Modal */}
      {selectedEvent && (
        <div
          data-testid="activity-details"
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setSelectedEvent(null)}
          onKeyDown={(e) => e.key === 'Escape' && setSelectedEvent(null)}
        >
          <div
            className="bg-bg-secondary rounded-2xl p-6 max-w-lg w-full mx-4 border border-border shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="modal-title" className="text-lg font-semibold text-text-primary mb-4">
              Event Details
            </h3>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-text-secondary">Type:</span>{' '}
                <span className="text-text-primary">{selectedEvent.type}</span>
              </div>
              <div>
                <span className="text-text-secondary">Time:</span>{' '}
                <span className="text-text-primary">{selectedEvent.timestamp}</span>
              </div>
              <div>
                <span className="text-text-secondary">Summary:</span>{' '}
                <span className="text-text-primary">{selectedEvent.summary}</span>
              </div>
              <div>
                <span className="text-text-secondary">Details:</span>
                <pre className="mt-2 p-2 bg-bg-tertiary rounded text-xs overflow-auto">
                  {JSON.stringify(selectedEvent.details, null, 2)}
                </pre>
              </div>
            </div>
            <button
              onClick={() => setSelectedEvent(null)}
              className="mt-4 w-full py-2 bg-accent-blue text-white rounded-lg hover:bg-accent-blue/80 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-blue focus:ring-offset-2"
              autoFocus
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
