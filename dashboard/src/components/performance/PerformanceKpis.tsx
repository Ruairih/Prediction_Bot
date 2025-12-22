/**
 * Performance KPIs Component
 */
import { PnlBadge } from '../common/PnlBadge';
import type { PerformanceStats } from '../../types';

export interface PerformanceKpisProps {
  stats: PerformanceStats;
}

export function PerformanceKpis({ stats }: PerformanceKpisProps) {
  return (
    <div
      data-testid="performance-kpis"
      className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6"
    >
      <div className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="text-text-secondary text-sm mb-1">Total P&L</div>
        <div className="text-2xl font-bold">
          <PnlBadge value={stats.totalPnl} size="lg" />
        </div>
      </div>

      <div className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="text-text-secondary text-sm mb-1">Win Rate</div>
        <div className="text-2xl font-bold text-text-primary">
          {(stats.winRate * 100).toFixed(1)}%
        </div>
      </div>

      <div className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="text-text-secondary text-sm mb-1">Sharpe Ratio</div>
        <div className="text-2xl font-bold text-text-primary">
          {stats.sharpeRatio.toFixed(2)}
        </div>
      </div>

      <div className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="text-text-secondary text-sm mb-1">Max Drawdown</div>
        <div className="text-2xl font-bold text-accent-red">
          {stats.maxDrawdownPercent.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}
