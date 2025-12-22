/**
 * Win/Loss Stats Component
 */
import type { PerformanceStats } from '../../types';

export interface WinLossStatsProps {
  stats: PerformanceStats;
}

export function WinLossStats({ stats }: WinLossStatsProps) {
  const winCount = Math.round(stats.totalTrades * stats.winRate);
  const lossCount = stats.totalTrades - winCount;

  return (
    <div
      data-testid="win-loss-stats"
      className="bg-bg-secondary rounded-lg p-4 border border-border"
    >
      <h3 className="text-lg font-semibold mb-4 text-text-primary">Win/Loss Statistics</h3>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-text-secondary text-sm mb-1">Winning Trades</div>
          <div className="text-xl font-bold text-accent-green">{winCount}</div>
        </div>

        <div>
          <div className="text-text-secondary text-sm mb-1">Losing Trades</div>
          <div className="text-xl font-bold text-accent-red">{lossCount}</div>
        </div>

        <div>
          <div className="text-text-secondary text-sm mb-1">Avg Win</div>
          <div className="text-xl font-bold text-accent-green">
            +${stats.avgWin.toFixed(2)}
          </div>
        </div>

        <div>
          <div className="text-text-secondary text-sm mb-1">Avg Loss</div>
          <div className="text-xl font-bold text-accent-red">
            -${Math.abs(stats.avgLoss).toFixed(2)}
          </div>
        </div>

        <div>
          <div className="text-text-secondary text-sm mb-1">Best Trade</div>
          <div className="text-xl font-bold text-accent-green">
            +${stats.bestTrade.toFixed(2)}
          </div>
        </div>

        <div>
          <div className="text-text-secondary text-sm mb-1">Worst Trade</div>
          <div className="text-xl font-bold text-accent-red">
            -${Math.abs(stats.worstTrade).toFixed(2)}
          </div>
        </div>

        <div className="col-span-2">
          <div className="text-text-secondary text-sm mb-1">Profit Factor</div>
          <div className="text-xl font-bold text-text-primary">
            {stats.profitFactor.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  );
}
