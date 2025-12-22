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
      className="bg-bg-secondary rounded-lg p-4 border border-border"
    >
      <h3 className="text-lg font-semibold mb-4 text-text-primary">Bot Status</h3>

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
            'flex-1 py-2 px-4 rounded-lg font-medium transition-colors',
            'bg-accent-yellow/20 text-accent-yellow hover:bg-accent-yellow/30'
          )}
        >
          ⏸ Pause
        </button>
        <button
          onClick={onStop}
          className={clsx(
            'flex-1 py-2 px-4 rounded-lg font-medium transition-colors',
            'bg-accent-red/20 text-accent-red hover:bg-accent-red/30'
          )}
        >
          ⬛ Stop
        </button>
      </div>
    </div>
  );
}
