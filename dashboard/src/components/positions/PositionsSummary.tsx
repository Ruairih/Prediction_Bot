/**
 * Positions Summary Component
 * Displays summary metrics for all positions
 */
import { PnlBadge } from '../common/PnlBadge';
import type { PositionSummary as PositionSummaryType } from '../../types';

export interface PositionsSummaryProps {
  summary: PositionSummaryType;
}

export function PositionsSummary({ summary }: PositionsSummaryProps) {
  return (
    <div
      data-testid="positions-summary"
      className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6"
    >
      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <div className="text-text-secondary text-sm mb-1">Open Positions</div>
        <div className="text-2xl font-bold text-text-primary">
          {summary.openCount}
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <div className="text-text-secondary text-sm mb-1">Total Exposure</div>
        <div className="text-2xl font-bold text-text-primary">
          ${summary.totalExposure.toFixed(2)}
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <div className="text-text-secondary text-sm mb-1">Unrealized P&L</div>
        <div className="text-2xl font-bold">
          <PnlBadge value={summary.totalUnrealizedPnl} size="lg" />
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <div className="text-text-secondary text-sm mb-1">Realized P&L</div>
        <div className="text-2xl font-bold">
          <PnlBadge value={summary.totalRealizedPnl} size="lg" />
        </div>
      </div>
    </div>
  );
}
