/**
 * Top Status Bar Component
 *
 * Premium always-visible command bar showing mode, health, and controls.
 */
import clsx from 'clsx';
import { formatDistanceToNowStrict } from 'date-fns';
import type { BotMode, ServiceStatusValue } from '../../types';

export interface StatusBarProps {
  mode: BotMode;
  balance: number;
  isConnected: boolean;
  lastHeartbeat?: string | null;
  healthStatus?: ServiceStatusValue;
  dbLatencyMs?: number | null;
  wsConnected?: boolean | null;
  onPause?: () => void;
  onResume?: () => void;
  onCancelAll?: () => void;
  onCloseAll?: () => void;
  onKillSwitch?: () => void;
}

export function StatusBar({
  mode,
  balance,
  isConnected,
  lastHeartbeat,
  healthStatus,
  dbLatencyMs,
  wsConnected,
  onPause,
  onResume,
  onCancelAll,
  onCloseAll,
  onKillSwitch,
}: StatusBarProps) {
  // wsConnected available for future use
  void wsConnected;

  const modeConfig = {
    live: {
      text: 'LIVE',
      className: 'bg-negative text-white shadow-glow-negative',
      pulse: true
    },
    dry_run: {
      text: 'PAPER',
      className: 'bg-warning text-black',
      pulse: false
    },
    paused: {
      text: 'PAUSED',
      className: 'bg-accent-secondary text-white',
      pulse: false
    },
    stopped: {
      text: 'OFFLINE',
      className: 'bg-bg-tertiary text-text-secondary border border-border',
      pulse: false
    },
  }[mode];

  let heartbeatLabel = 'n/a';
  if (lastHeartbeat) {
    const parsed = new Date(lastHeartbeat);
    if (!Number.isNaN(parsed.getTime())) {
      heartbeatLabel = `${formatDistanceToNowStrict(parsed)} ago`;
    }
  }

  const healthConfig = {
    healthy: { color: 'text-positive', dot: 'bg-positive' },
    degraded: { color: 'text-warning', dot: 'bg-warning' },
    unhealthy: { color: 'text-negative', dot: 'bg-negative' },
    unknown: { color: 'text-text-muted', dot: 'bg-text-muted' },
  }[healthStatus ?? 'unknown'];

  return (
    <header className="relative h-14 bg-bg-secondary/95 border-b border-border flex items-center justify-between px-4 backdrop-blur-glass">
      {/* Decorative gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-primary/30 to-transparent" />

      {/* Left: Mode + health indicators */}
      <div className="flex items-center gap-4">
        {/* Mode badge */}
        <div
          data-testid="mode-indicator"
          className={clsx(
            'relative px-3 py-1 rounded-md text-[10px] font-bold tracking-[0.15em]',
            modeConfig.className
          )}
        >
          {modeConfig.pulse && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-negative animate-ping" />
          )}
          {modeConfig.text}
        </div>

        {/* Status indicators */}
        <div className="hidden sm:flex items-center gap-3 text-xs">
          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            <span className={clsx(
              'w-1.5 h-1.5 rounded-full',
              isConnected ? 'bg-positive' : 'bg-negative'
            )} />
            <span className={isConnected ? 'text-text-secondary' : 'text-negative'}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          <span className="text-border">•</span>

          {/* System health */}
          <div className="flex items-center gap-1.5">
            <span className={clsx('w-1.5 h-1.5 rounded-full', healthConfig.dot)} />
            <span className={healthConfig.color}>
              {healthStatus ?? 'Unknown'}
            </span>
          </div>

          {/* DB Latency */}
          {typeof dbLatencyMs === 'number' && (
            <>
              <span className="text-border">•</span>
              <span className={clsx(
                'font-mono',
                dbLatencyMs < 50 ? 'text-positive' : dbLatencyMs < 100 ? 'text-warning' : 'text-negative'
              )}>
                {Math.round(dbLatencyMs)}ms
              </span>
            </>
          )}

          {/* Heartbeat */}
          <span className="hidden lg:flex items-center gap-1 text-text-muted">
            <span className="text-border">•</span>
            <span>↻ {heartbeatLabel}</span>
          </span>
        </div>
      </div>

      {/* Center: Branding (hidden on small screens) */}
      <div className="hidden xl:flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-gradient-primary flex items-center justify-center text-white text-xs font-bold">
          P
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-[0.3em] text-text-muted">Trading</div>
          <div className="text-sm font-semibold text-text-primary -mt-0.5">Command Desk</div>
        </div>
      </div>

      {/* Right: Balance + controls */}
      <div className="flex items-center gap-4">
        {/* Balance display */}
        <div data-testid="balance-display" className="text-right">
          <div className="text-[9px] uppercase tracking-[0.2em] text-text-muted">
            Available
          </div>
          <div className="text-sm font-semibold text-text-primary tabular-nums">
            ${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        {/* Control buttons */}
        <div className="flex items-center gap-1.5">
          {mode === 'paused' ? (
            <button
              onClick={onResume}
              className="btn btn-secondary text-xs py-1.5 px-3"
            >
              Resume
            </button>
          ) : (
            <button
              onClick={onPause}
              className="btn btn-ghost text-xs py-1.5 px-3"
            >
              Pause
            </button>
          )}

          <button
            onClick={onCancelAll}
            className="btn btn-ghost text-xs py-1.5 px-3 hidden md:flex"
          >
            Cancel
          </button>

          <button
            onClick={onCloseAll}
            className="btn btn-ghost text-xs py-1.5 px-3 text-warning hover:text-warning hidden md:flex"
          >
            Flatten
          </button>

          {mode === 'live' && onKillSwitch && (
            <button
              onClick={onKillSwitch}
              className="btn btn-danger text-xs py-1.5 px-3"
            >
              Kill
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
