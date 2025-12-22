/**
 * Top Status Bar Component
 *
 * Always visible bar showing mode, balance, and global controls.
 */
import clsx from 'clsx';
import type { BotMode } from '../../types';

export interface StatusBarProps {
  mode: BotMode;
  balance: number;
  isConnected: boolean;
  onKillSwitch?: () => void;
}

export function StatusBar({ mode, balance, isConnected, onKillSwitch }: StatusBarProps) {
  const modeDisplay = {
    live: { text: 'LIVE', color: 'bg-accent-red text-white' },
    dry_run: { text: 'DRY RUN', color: 'bg-accent-yellow text-black' },
    paused: { text: 'PAUSED', color: 'bg-accent-purple text-white' },
    stopped: { text: 'STOPPED', color: 'bg-text-secondary text-white' },
  }[mode];

  return (
    <header className="h-14 bg-bg-secondary border-b border-border flex items-center justify-between px-4">
      {/* Left: Mode indicator */}
      <div className="flex items-center gap-4">
        <div
          data-testid="mode-indicator"
          className={clsx(
            'px-3 py-1 rounded-full text-sm font-bold',
            modeDisplay.color
          )}
        >
          {modeDisplay.text}
        </div>

        {/* Connection status */}
        <div className="flex items-center gap-2">
          <div
            className={clsx(
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-accent-green' : 'bg-accent-red'
            )}
          />
          <span className="text-text-secondary text-sm">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Center: Title (optional) */}
      <div className="hidden md:block text-text-secondary text-sm">
        Polymarket Trading Bot
      </div>

      {/* Right: Balance and controls */}
      <div className="flex items-center gap-4">
        <div data-testid="balance-display" className="text-lg font-mono">
          <span className="text-text-secondary">$</span>
          <span className="text-text-primary">{balance.toFixed(2)}</span>
        </div>

        {mode === 'live' && onKillSwitch && (
          <button
            onClick={onKillSwitch}
            className="px-3 py-1 bg-accent-red text-white rounded-lg text-sm font-medium hover:bg-accent-red/80 transition-colors"
          >
            KILL SWITCH
          </button>
        )}
      </div>
    </header>
  );
}
