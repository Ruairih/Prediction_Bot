/**
 * Time Range Selector Component
 */
import clsx from 'clsx';
import type { TimeRange } from '../../types';

const ranges: { value: TimeRange; label: string }[] = [
  { value: '1d', label: '1D' },
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: 'all', label: 'All' },
];

export interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  return (
    <div
      data-testid="time-range-selector"
      className="flex items-center gap-1 bg-bg-tertiary rounded-lg p-1"
    >
      {ranges.map((range) => (
        <button
          key={range.value}
          onClick={() => onChange(range.value)}
          className={clsx(
            'px-3 py-1 rounded text-sm font-medium transition-colors',
            value === range.value
              ? 'bg-accent-blue text-white'
              : 'text-text-secondary hover:text-text-primary'
          )}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}
