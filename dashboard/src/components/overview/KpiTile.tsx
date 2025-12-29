/**
 * KPI Tile Component
 *
 * Premium key performance indicator tile with glow effects and animations.
 */
import clsx from 'clsx';

export interface KpiTileProps {
  label: string;
  value: string;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
  testId: string;
  icon?: string;
}

export function KpiTile({ label, value, change, trend, testId, icon }: KpiTileProps) {
  const isPositive = trend === 'up';
  const isNegative = trend === 'down';

  return (
    <div
      data-testid={testId}
      className={clsx(
        'kpi-tile group',
        isPositive && 'hover:shadow-glow-positive',
        isNegative && 'hover:shadow-glow-negative',
        !trend && 'hover:shadow-glow-primary'
      )}
    >
      {/* Decorative glow */}
      <div className={clsx(
        'kpi-decoration transition-opacity duration-300',
        'group-hover:opacity-80',
        isPositive && '!bg-positive/20',
        isNegative && '!bg-negative/20'
      )} />

      {/* Top accent line on hover */}
      <div className={clsx(
        'absolute top-0 left-0 right-0 h-[2px] opacity-0 group-hover:opacity-100 transition-opacity',
        isPositive && 'bg-positive',
        isNegative && 'bg-negative',
        !trend && 'bg-gradient-primary'
      )} />

      {/* Label */}
      <div className="kpi-label flex items-center gap-2">
        {icon && <span className="text-sm opacity-60">{icon}</span>}
        <span>{label}</span>
      </div>

      {/* Value */}
      <div className={clsx(
        'kpi-value tabular-nums',
        isPositive && 'text-positive text-glow-positive',
        isNegative && 'text-negative text-glow-negative',
        !trend && 'text-text-primary'
      )}>
        {value}
      </div>

      {/* Change indicator */}
      {change && (
        <div className={clsx(
          'kpi-change',
          isPositive && 'text-positive',
          isNegative && 'text-negative',
          !trend && 'text-text-secondary'
        )}>
          {isPositive && (
            <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
              <path d="M6 2L10 7H2L6 2Z" />
            </svg>
          )}
          {isNegative && (
            <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
              <path d="M6 10L2 5H10L6 10Z" />
            </svg>
          )}
          <span className="font-medium">{change}</span>
        </div>
      )}
    </div>
  );
}
