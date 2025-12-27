/**
 * Bot Status Component
 *
 * Displays current bot status with intervention controls.
 */
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import type { BotStatus as BotStatusType } from '../../types';

export interface BotStatusProps {
  status: BotStatusType;
  onPause: () => void;
  onStop: () => void;
}

export function BotStatus({ status, onPause, onStop }: BotStatusProps) {
  const statusColor = {
    healthy: 'bg-accent-green',
    degraded: 'bg-accent-yellow',
    unhealthy: 'bg-accent-red',
  }[status.status];

  const statusText = {
    live: 'Running (LIVE)',
    dry_run: 'Running (DRY RUN)',
    paused: 'Paused',
    stopped: 'Stopped',
  }[status.mode];

  const lastTradeText = status.lastTradeTime
    ? formatDistanceToNow(new Date(status.lastTradeTime), { addSuffix: true })
    : 'No trades yet';

  return (
    <div
      data-testid="bot-status"
      className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm"
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            System
          </div>
          <h3 className="text-lg font-semibold text-text-primary">Bot Status</h3>
        </div>
        <div className="text-xs text-text-secondary">v{status.version}</div>
      </div>

      <div className="space-y-3">
        {/* Status Row */}
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Status</span>
          <div className="flex items-center gap-2">
            <div
              data-testid="status-indicator"
              className={clsx('w-2 h-2 rounded-full', statusColor)}
            />
            <span className="text-text-primary">{statusText}</span>
          </div>
        </div>

        {/* Last Trade Row */}
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Last trade</span>
          <span className="text-text-primary">{lastTradeText}</span>
        </div>

        {/* WebSocket Row */}
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">WebSocket</span>
          <span
            className={clsx(
              status.websocketConnected ? 'text-accent-green' : 'text-accent-red'
            )}
          >
            {status.websocketConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        {/* Error Rate Row (only if non-zero) */}
        {status.errorRate > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Error rate</span>
            <span className="text-accent-yellow">
              {(status.errorRate * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {/* Control Buttons */}
      <div className="flex gap-2 mt-4 pt-4 border-t border-border">
        <button
          onClick={onPause}
          className={clsx(
            'flex-1 py-2 px-4 rounded-full font-semibold text-xs transition-colors',
            'bg-accent-yellow/15 text-accent-yellow hover:bg-accent-yellow/25'
          )}
        >
          {status.mode === 'paused' ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={onStop}
          className={clsx(
            'flex-1 py-2 px-4 rounded-full font-semibold text-xs transition-colors',
            'bg-accent-red/15 text-accent-red hover:bg-accent-red/25'
          )}
        >
          Stop
        </button>
      </div>
    </div>
  );
}
