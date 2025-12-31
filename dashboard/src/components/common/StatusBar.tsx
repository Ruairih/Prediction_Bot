/**
 * Top Status Bar Component
 *
 * Premium always-visible command bar showing mode, health, and controls.
 * Responsive design with hamburger menu for mobile navigation.
 */
import { useState } from 'react';
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
  onMobileMenuToggle?: () => void;
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
  onMobileMenuToggle,
}: StatusBarProps) {
  const [mobileControlsOpen, setMobileControlsOpen] = useState(false);

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
    <header className="relative bg-bg-secondary/95 border-b border-border backdrop-blur-glass">
      {/* Decorative gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-primary/30 to-transparent" />

      {/* Main status bar row */}
      <div className="h-14 flex items-center justify-between px-3 md:px-4">
        {/* Left: Hamburger (mobile) + Mode + health indicators */}
        <div className="flex items-center gap-2 md:gap-4">
          {/* Hamburger menu button - visible only on mobile */}
          <button
            onClick={onMobileMenuToggle}
            className="md:hidden p-2 -ml-1 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            aria-label="Open navigation menu"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Mode badge */}
          <div
            data-testid="mode-indicator"
            role="status"
            aria-label={`Trading mode: ${modeConfig.text}${modeConfig.pulse ? ', active' : ''}`}
            className={clsx(
              'relative px-2 md:px-3 py-1 rounded-md text-[10px] font-bold tracking-[0.15em]',
              modeConfig.className
            )}
          >
            {modeConfig.pulse && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-negative animate-ping" aria-hidden="true" />
            )}
            {modeConfig.text}
          </div>

          {/* Status indicators - hidden on mobile, visible on sm+ */}
          <div className="hidden sm:flex items-center gap-3 text-xs">
            {/* Connection status */}
            <div className="flex items-center gap-1.5">
              <span
                className={clsx(
                  'w-1.5 h-1.5 rounded-full',
                  isConnected ? 'bg-positive' : 'bg-negative'
                )}
                aria-hidden="true"
              />
              <span className={isConnected ? 'text-text-secondary' : 'text-negative'}>
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>

            <span className="text-border" aria-hidden="true">|</span>

            {/* System health */}
            <div className="flex items-center gap-1.5">
              <span className={clsx('w-1.5 h-1.5 rounded-full', healthConfig.dot)} aria-hidden="true" />
              <span className={healthConfig.color}>
                {healthStatus ?? 'Unknown'}
              </span>
            </div>

            {/* DB Latency - hidden on small tablets */}
            {typeof dbLatencyMs === 'number' && (
              <span className={clsx(
                'hidden md:inline font-mono',
                dbLatencyMs < 50 ? 'text-positive' : dbLatencyMs < 100 ? 'text-warning' : 'text-negative'
              )}>
                {Math.round(dbLatencyMs)}ms
              </span>
            )}

            {/* Heartbeat - only on large screens */}
            <span className="hidden lg:flex items-center gap-1 text-text-muted">
              <span className="text-border">|</span>
              <span>Last: {heartbeatLabel}</span>
            </span>
          </div>
        </div>

        {/* Center: Branding (hidden on smaller screens) */}
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
        <div className="flex items-center gap-2 md:gap-4">
          {/* Balance display - compact on mobile */}
          <div data-testid="balance-display" className="text-right">
            <div className="hidden sm:block text-[9px] uppercase tracking-[0.2em] text-text-muted">
              Available
            </div>
            <div className="text-sm font-semibold text-text-primary tabular-nums">
              ${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Desktop control buttons */}
          <div className="hidden md:flex items-center gap-1.5">
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
              className="btn btn-ghost text-xs py-1.5 px-3"
            >
              Cancel
            </button>

            <button
              onClick={onCloseAll}
              className="btn btn-ghost text-xs py-1.5 px-3 text-warning hover:text-warning"
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

          {/* Mobile controls dropdown trigger */}
          <button
            onClick={() => setMobileControlsOpen(!mobileControlsOpen)}
            className="md:hidden p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            aria-label="Open controls menu"
            aria-expanded={mobileControlsOpen}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile controls dropdown */}
      {mobileControlsOpen && (
        <div className="md:hidden absolute top-full right-0 mt-1 mr-2 z-50 bg-bg-secondary border border-border rounded-lg shadow-lg overflow-hidden">
          <div className="p-2 space-y-1 min-w-[140px]">
            {/* Status info for mobile */}
            <div className="px-3 py-2 text-xs text-text-muted border-b border-border mb-1">
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className={clsx(
                    'w-1.5 h-1.5 rounded-full',
                    isConnected ? 'bg-positive' : 'bg-negative'
                  )}
                  aria-hidden="true"
                />
                <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className={clsx('w-1.5 h-1.5 rounded-full', healthConfig.dot)} aria-hidden="true" />
                <span>{healthStatus ?? 'Unknown'}</span>
              </div>
            </div>

            {mode === 'paused' ? (
              <button
                onClick={() => { onResume?.(); setMobileControlsOpen(false); }}
                className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-tertiary rounded"
              >
                Resume Trading
              </button>
            ) : (
              <button
                onClick={() => { onPause?.(); setMobileControlsOpen(false); }}
                className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-tertiary rounded"
              >
                Pause Trading
              </button>
            )}

            <button
              onClick={() => { onCancelAll?.(); setMobileControlsOpen(false); }}
              className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-tertiary rounded"
            >
              Cancel All Orders
            </button>

            <button
              onClick={() => { onCloseAll?.(); setMobileControlsOpen(false); }}
              className="w-full text-left px-3 py-2 text-sm text-warning hover:bg-bg-tertiary rounded"
            >
              Flatten Positions
            </button>

            {mode === 'live' && onKillSwitch && (
              <button
                onClick={() => { onKillSwitch(); setMobileControlsOpen(false); }}
                className="w-full text-left px-3 py-2 text-sm text-negative hover:bg-bg-tertiary rounded"
              >
                Kill Switch
              </button>
            )}
          </div>
        </div>
      )}

      {/* Mobile controls backdrop */}
      {mobileControlsOpen && (
        <div
          className="md:hidden fixed inset-0 z-40"
          onClick={() => setMobileControlsOpen(false)}
          aria-hidden="true"
        />
      )}
    </header>
  );
}
