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
    'text-2xl font-bold value',
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
      className="bg-bg-secondary rounded-lg p-4 border border-border"
    >
      <div className="text-text-secondary text-sm mb-1">{label}</div>
      <div className={valueClasses}>{value}</div>
      {change && (
        <div className={changeClasses}>
          {trend === 'up' && '↑ '}
          {trend === 'down' && '↓ '}
          {change}
        </div>
      )}
    </div>
  );
}
