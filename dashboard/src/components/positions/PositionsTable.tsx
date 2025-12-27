/**
 * Positions Table Component
 */
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { PnlBadge } from '../common/PnlBadge';
import type { Position, PositionFilterState } from '../../types';

export interface PositionsTableProps {
  positions: Position[];
  sortBy: PositionFilterState['sortBy'];
  sortDir: PositionFilterState['sortDir'];
  onSort: (column: PositionFilterState['sortBy']) => void;
  onClose: (position: Position) => void;
  onAdjust: (position: Position) => void;
}

export function PositionsTable({
  positions,
  sortBy,
  sortDir,
  onSort,
  onClose,
  onAdjust,
}: PositionsTableProps) {
  const getSortIndicator = (column: PositionFilterState['sortBy']) => {
    if (sortBy !== column) return null;
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  const getAriaSort = (column: PositionFilterState['sortBy']): 'ascending' | 'descending' | 'none' => {
    if (sortBy !== column) return 'none';
    return sortDir === 'asc' ? 'ascending' : 'descending';
  };

  return (
    <div data-testid="positions-table" className="bg-bg-secondary rounded-2xl border border-border overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-bg-tertiary">
            <tr>
              <th
                className="px-4 py-3 text-left text-sm font-medium text-text-secondary cursor-pointer hover:text-text-primary"
                onClick={() => onSort('entryTime')}
                aria-sort={getAriaSort('entryTime')}
              >
                Market{getSortIndicator('entryTime')}
              </th>
              <th
                className="px-4 py-3 text-right text-sm font-medium text-text-secondary cursor-pointer hover:text-text-primary"
                onClick={() => onSort('size')}
                aria-sort={getAriaSort('size')}
              >
                Size{getSortIndicator('size')}
              </th>
              <th className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Entry
              </th>
              <th className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Current
              </th>
              <th
                className="px-4 py-3 text-right text-sm font-medium text-text-secondary cursor-pointer hover:text-text-primary"
                onClick={() => onSort('unrealizedPnl')}
                aria-sort={getAriaSort('unrealizedPnl')}
              >
                P&L{getSortIndicator('unrealizedPnl')}
              </th>
              <th className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {positions.map((position) => (
              <tr
                key={position.positionId}
                data-testid="position-row"
                className="hover:bg-bg-tertiary/50 transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="max-w-xs">
                    <div className="text-sm text-text-primary truncate">
                      {position.question}
                    </div>
                    <div className="text-xs text-text-secondary">
                      {formatDistanceToNow(new Date(position.entryTime), { addSuffix: true })}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  {position.size}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  ${position.entryPrice.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  ${position.currentPrice.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right">
                  <div data-testid="position-pnl" className={clsx(
                    'text-sm font-medium',
                    position.unrealizedPnl > 0 && 'text-accent-green',
                    position.unrealizedPnl < 0 && 'text-accent-red',
                    position.unrealizedPnl === 0 && 'text-text-secondary'
                  )}>
                    <PnlBadge value={position.unrealizedPnl} />
                    <span className="text-xs text-text-secondary ml-1">
                      ({position.pnlPercent > 0 ? '+' : ''}{position.pnlPercent.toFixed(1)}%)
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => onAdjust(position)}
                      aria-label={`Limit exit for ${position.question}`}
                      className="px-2 py-1 text-xs bg-accent-blue/20 text-accent-blue rounded hover:bg-accent-blue/30 transition-colors"
                    >
                      Exit Limit
                    </button>
                    <button
                      onClick={() => onClose(position)}
                      aria-label={`Close position for ${position.question}`}
                      className="px-2 py-1 text-xs bg-accent-red/20 text-accent-red rounded hover:bg-accent-red/30 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
