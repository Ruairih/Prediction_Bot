/**
 * Overview Page - Mission Control
 *
 * Main dashboard with KPIs, bot status, activity stream, and charts.
 * Fetches real data from the Flask monitoring API.
 */
import { useState } from 'react';
import { KpiTile } from '../components/overview/KpiTile';
import { BotStatus } from '../components/overview/BotStatus';
import { ActivityStream } from '../components/overview/ActivityStream';
import { useBotStatus, useMetrics, useTriggers } from '../hooks/useDashboardData';
import type { BotStatus as BotStatusType, DashboardMetrics, ActivityEvent } from '../types';

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
  const { data: activityData, isLoading: activityLoading } = useTriggers(20);

  // Use API data or fallbacks
  const status = statusData ?? fallbackStatus;
  const metrics = metricsData ?? fallbackMetrics;
  const activity = activityData ?? [];

  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);

  const handlePause = () => {
    console.log('Pause clicked');
    // TODO: Implement pause API call
  };

  const handleStop = () => {
    console.log('Stop clicked');
    // TODO: Implement stop API call
  };

  const pnlTrend = metrics.totalPnl >= 0 ? 'up' : 'down';
  const todayTrend = metrics.todayPnl >= 0 ? 'up' : 'down';

  // Show connection status
  const isConnected = !statusError && !metricsError;
  const isLoading = statusLoading || metricsLoading;

  return (
    <div className="p-6 space-y-6">
      {/* Page Title */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Overview</h1>
          <p className="text-text-secondary">Mission control for your trading bot</p>
        </div>

        {/* Connection Status */}
        <div className="flex items-center gap-2">
          {isLoading && (
            <span className="text-text-secondary text-sm">Loading...</span>
          )}
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-text-secondary text-sm">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Error Banner */}
      {(statusError || metricsError) && (
        <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
          <p className="text-red-400">
            Unable to connect to monitoring API. Make sure the bot is running on port 5050.
          </p>
          <p className="text-red-400/70 text-sm mt-1">
            Run: <code className="bg-red-900/30 px-1 rounded">python -m polymarket_bot.main --mode all</code>
          </p>
        </div>
      )}

      {/* KPI Tiles */}
      <div data-testid="kpi-container" className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity Stream - Takes 2 columns on large screens */}
        <div className="lg:col-span-2">
          <ActivityStream
            events={activity}
            maxEvents={10}
            onEventClick={setSelectedEvent}
            isLoading={activityLoading}
          />
        </div>

        {/* Bot Status */}
        <div>
          <BotStatus
            status={status}
            onPause={handlePause}
            onStop={handleStop}
          />
        </div>
      </div>

      {/* Equity Curve Placeholder */}
      <div
        data-testid="equity-curve"
        className="bg-bg-secondary rounded-lg p-4 border border-border"
      >
        <h3 className="text-lg font-semibold mb-4 text-text-primary">
          Equity Curve (Last 30 Days)
        </h3>
        <div className="h-64 flex items-center justify-center text-text-secondary">
          {/* TODO: Replace with Recharts implementation using real daily_pnl data */}
          <svg viewBox="0 0 400 200" className="w-full h-full">
            <polyline
              fill="none"
              stroke={metrics.totalPnl >= 0 ? '#3fb950' : '#f85149'}
              strokeWidth="2"
              points="0,180 50,170 100,160 150,150 200,140 250,120 300,100 350,80 400,60"
            />
            <text x="10" y="20" fill="#8b949e" fontSize="12">
              ${(metrics.availableBalance + metrics.capitalDeployed).toFixed(0)}
            </text>
            <text x="10" y="100" fill="#8b949e" fontSize="12">
              ${((metrics.availableBalance + metrics.capitalDeployed) * 0.9).toFixed(0)}
            </text>
            <text x="10" y="180" fill="#8b949e" fontSize="12">
              ${((metrics.availableBalance + metrics.capitalDeployed) * 0.8).toFixed(0)}
            </text>
          </svg>
        </div>
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
            className="bg-bg-secondary rounded-lg p-6 max-w-lg w-full mx-4 border border-border"
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
