/**
 * KPI Tile Component
 *
 * Displays a key performance indicator with optional trend and change.
 */
import clsx from 'clsx';

export interface KpiTileProps {
  label: string;
  value: string;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
  testId: string;
}

export function KpiTile({ label, value, change, trend, testId }: KpiTileProps) {
  const valueClasses = clsx(
    'text-2xl font-semibold value',
    {
      'text-accent-green': trend === 'up',
      'text-accent-red': trend === 'down',
      'text-text-primary': !trend || trend === 'neutral',
    }
  );

  const changeClasses = clsx(
    'text-sm mt-1',
    {
      'text-accent-green': trend === 'up',
      'text-accent-red': trend === 'down',
      'text-text-secondary': !trend || trend === 'neutral',
    }
  );

  return (
    <div
      data-testid={testId}
      className="relative overflow-hidden rounded-2xl border border-border bg-bg-secondary p-4 shadow-sm"
    >
      <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70 mb-2">
        {label}
      </div>
      <div className={valueClasses}>{value}</div>
      {change && (
        <div className={changeClasses}>
          {trend === 'up' && 'UP '}
          {trend === 'down' && 'DOWN '}
          {change}
        </div>
      )}
      <div className="absolute -right-8 -top-8 h-16 w-16 rounded-full bg-accent-blue/10" />
    </div>
  );
}
