/**
 * P&L Badge Component
 * Displays profit/loss with appropriate coloring
 */
import clsx from 'clsx';

export interface PnlBadgeProps {
  value: number;
  format?: 'currency' | 'percent';
  showSign?: boolean;
  size?: 'sm' | 'md' | 'lg';
  testId?: string;
}

export function PnlBadge({
  value,
  format = 'currency',
  showSign = true,
  size = 'md',
  testId,
}: PnlBadgeProps) {
  const isPositive = value > 0;
  const isNegative = value < 0;

  const formattedValue = format === 'currency'
    ? `$${Math.abs(value).toFixed(2)}`
    : `${Math.abs(value).toFixed(2)}%`;

  const prefix = showSign ? (isPositive ? '+' : isNegative ? '-' : '') : (isNegative ? '-' : '');

  const sizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base font-semibold',
  };

  return (
    <span
      data-testid={testId}
      className={clsx(
        sizeClasses[size],
        isPositive && 'text-accent-green',
        isNegative && 'text-accent-red',
        !isPositive && !isNegative && 'text-text-secondary'
      )}
    >
      {prefix}{formattedValue}
    </span>
  );
}
