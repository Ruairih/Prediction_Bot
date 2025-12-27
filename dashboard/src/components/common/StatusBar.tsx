/**
 * Top Status Bar Component
 *
 * Always visible command bar showing mode, health, and controls.
 */
import clsx from 'clsx';
import { formatDistanceToNowStrict } from 'date-fns';
import type { BotMode } from '../../types';

export interface StatusBarProps {
  mode: BotMode;
  balance: number;
  isConnected: boolean;
  lastHeartbeat?: string | null;
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
  onPause,
  onResume,
  onCancelAll,
  onCloseAll,
  onKillSwitch,
}: StatusBarProps) {
  const modeDisplay = {
    live: { text: 'LIVE', color: 'bg-accent-red text-white' },
    dry_run: { text: 'PAPER', color: 'bg-accent-yellow text-white' },
    paused: { text: 'PAUSED', color: 'bg-accent-purple text-white' },
    stopped: { text: 'OFFLINE', color: 'bg-border text-text-primary' },
  }[mode];

  let heartbeatLabel = 'n/a';
  if (lastHeartbeat) {
    const parsed = new Date(lastHeartbeat);
    if (!Number.isNaN(parsed.getTime())) {
      heartbeatLabel = `${formatDistanceToNowStrict(parsed)} ago`;
    }
  }

  return (
    <header className="h-16 bg-bg-secondary/90 border-b border-border flex items-center justify-between px-6 backdrop-blur">
      {/* Left: Mode + health */}
      <div className="flex items-center gap-4">
        <div
          data-testid="mode-indicator"
          className={clsx(
            'px-3 py-1 rounded-full text-xs font-semibold tracking-widest',
            modeDisplay.color
          )}
        >
          {modeDisplay.text}
        </div>

        <div className="flex items-center gap-2 text-sm text-text-secondary">
          <span
            className={clsx(
              'h-2 w-2 rounded-full',
              isConnected ? 'bg-accent-green' : 'bg-accent-red'
            )}
          />
          <span>{isConnected ? 'Live feed' : 'Feed down'}</span>
          <span className="text-text-secondary/70">|</span>
          <span>Heartbeat {heartbeatLabel}</span>
        </div>
      </div>

      {/* Center: Title */}
      <div className="hidden lg:flex items-center gap-3 text-sm text-text-secondary">
        <span className="uppercase tracking-[0.3em] text-[10px] text-text-secondary/70">
          Polymarket
        </span>
        <span className="text-text-primary font-semibold">Trading Command</span>
      </div>

      {/* Right: Balance + controls */}
      <div className="flex items-center gap-3">
        <div data-testid="balance-display" className="text-sm">
          <div className="text-text-secondary text-[11px] uppercase tracking-[0.2em]">
            Available
          </div>
          <div className="text-text-primary font-semibold tabular-nums">
            ${balance.toFixed(2)} USDC
          </div>
        </div>

        <div className="flex items-center gap-2">
          {mode === 'paused' ? (
            <button
              onClick={onResume}
              className="px-3 py-1 text-xs font-semibold border border-border rounded-full hover:border-accent-blue hover:text-accent-blue transition-colors"
            >
              Resume
            </button>
          ) : (
            <button
              onClick={onPause}
              className="px-3 py-1 text-xs font-semibold border border-border rounded-full hover:border-accent-blue hover:text-accent-blue transition-colors"
            >
              Pause
            </button>
          )}
          <button
            onClick={onCancelAll}
            className="px-3 py-1 text-xs font-semibold border border-border rounded-full hover:border-accent-yellow hover:text-accent-yellow transition-colors"
          >
            Cancel All
          </button>
          <button
            onClick={onCloseAll}
            className="px-3 py-1 text-xs font-semibold border border-border rounded-full hover:border-accent-red hover:text-accent-red transition-colors"
          >
            Flatten
          </button>
          {mode === 'live' && onKillSwitch && (
            <button
              onClick={onKillSwitch}
              className="px-3 py-1 text-xs font-semibold bg-accent-red text-white rounded-full hover:bg-accent-red/90 transition-colors"
            >
              Kill
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
