/**
 * Pipeline Page
 *
 * Shows visibility into the trading pipeline:
 * - Rejection funnel (why markets are filtered)
 * - Candidate markets (close to threshold)
 * - Near-misses (almost triggered)
 */
import { useState } from 'react';
import { EmptyState } from '../components/common/EmptyState';
import {
  usePipelineFunnel,
  usePipelineRejections,
  usePipelineCandidates,
  useNearMisses,
} from '../hooks/useDashboardData';
import type { RejectionStage, RejectionEvent, CandidateMarket } from '../types';

// Stage colors for the funnel visualization
const stageColors: Record<RejectionStage, string> = {
  threshold: 'bg-gray-500',
  duplicate: 'bg-blue-500',
  g1_trade_age: 'bg-yellow-500',
  g5_orderbook: 'bg-orange-500',
  g6_weather: 'bg-purple-500',
  time_to_end: 'bg-red-400',
  trade_size: 'bg-pink-400',
  category: 'bg-indigo-400',
  manual_block: 'bg-gray-600',
  max_positions: 'bg-teal-500',
  strategy_hold: 'bg-cyan-400',
  strategy_ignore: 'bg-slate-400',
};

export function Pipeline() {
  const [selectedStage, setSelectedStage] = useState<RejectionStage | null>(null);
  const [timeWindow, setTimeWindow] = useState(60);

  const { data: funnel, isLoading: funnelLoading, error: funnelError } = usePipelineFunnel(timeWindow);
  const { data: rejections } = usePipelineRejections(50, selectedStage ?? undefined);
  const { data: candidates } = usePipelineCandidates(30, 'distance');
  const { data: nearMisses } = useNearMisses(0.02);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Pipeline</h1>
          <p className="text-text-secondary">
            Understand why markets are filtered and track near-misses
          </p>
        </div>

        {/* Time window selector */}
        <div className="flex gap-2">
          {[15, 60, 360].map((mins) => (
            <button
              key={mins}
              onClick={() => setTimeWindow(mins)}
              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                timeWindow === mins
                  ? 'bg-accent-primary text-white'
                  : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {mins < 60 ? `${mins}m` : `${mins / 60}h`}
            </button>
          ))}
        </div>
      </div>

      {/* Error Banner */}
      {funnelError && (
        <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
          <p className="text-red-400">
            Unable to load pipeline data. Make sure the bot is running.
          </p>
        </div>
      )}

      {/* Stats Row */}
      {funnel && (
        <div className="grid grid-cols-4 gap-4">
          <StatCard
            label="Total Rejections"
            value={funnel.totalRejections.toLocaleString()}
            subtext={`Last ${timeWindow}m`}
          />
          <StatCard
            label="Candidates Watching"
            value={funnel.candidateCount.toString()}
            subtext="Markets in pipeline"
          />
          <StatCard
            label="Near Misses"
            value={funnel.nearMissCount.toString()}
            subtext="Within 2% of threshold"
            highlight={funnel.nearMissCount > 0}
          />
          <StatCard
            label="Top Rejection"
            value={funnel.funnel[0]?.label ?? 'N/A'}
            subtext={`${funnel.funnel[0]?.percentage.toFixed(1) ?? 0}%`}
          />
        </div>
      )}

      {/* Rejection Funnel */}
      <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
        <h2 className="text-lg font-semibold text-text-primary mb-4">Rejection Funnel</h2>

        {funnelLoading ? (
          <div className="text-center py-8 text-text-secondary">Loading...</div>
        ) : !funnel ? (
          <EmptyState title="No data" description="Start the bot to see pipeline data" icon="📊" />
        ) : (
          <div className="space-y-2">
            {funnel.funnel
              .filter((item) => item.count > 0)
              .map((item) => (
                <button
                  key={item.stage}
                  onClick={() => setSelectedStage(selectedStage === item.stage ? null : item.stage)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg transition-colors ${
                    selectedStage === item.stage
                      ? 'bg-bg-tertiary ring-1 ring-accent-primary'
                      : 'hover:bg-bg-tertiary'
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full ${stageColors[item.stage]}`} />
                  <span className="flex-1 text-left text-sm text-text-primary">{item.label}</span>
                  <span className="text-text-secondary text-sm w-24 text-right">
                    {item.count.toLocaleString()}
                  </span>
                  <span className="text-text-secondary text-sm w-16 text-right">
                    {item.percentage.toFixed(1)}%
                  </span>
                  <div className="w-40 h-2 bg-bg-tertiary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${stageColors[item.stage]}`}
                      style={{ width: `${Math.min(item.percentage, 100)}%` }}
                    />
                  </div>
                </button>
              ))}
          </div>
        )}
      </section>

      {/* Selected Stage Details */}
      {selectedStage && (
        <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-text-primary">
              Recent {selectedStage.replace(/_/g, ' ')} Rejections
            </h2>
            <button
              onClick={() => setSelectedStage(null)}
              className="text-text-secondary hover:text-text-primary text-sm"
            >
              Clear
            </button>
          </div>

          {rejections && rejections.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-secondary border-b border-border">
                    <th className="pb-2 font-medium">Time</th>
                    <th className="pb-2 font-medium">Market</th>
                    <th className="pb-2 font-medium text-right">Price</th>
                    <th className="pb-2 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {rejections.map((r, i) => (
                    <RejectionRow key={`${r.tokenId}-${r.timestamp}-${i}`} rejection={r} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No samples recorded"
              description={`No ${selectedStage.replace(/_/g, ' ')} rejections have been sampled yet. The bot samples 1 in 10 rejections to conserve memory.`}
              icon="📭"
            />
          )}
        </section>
      )}

      {/* Near Misses */}
      {nearMisses && nearMisses.length > 0 && (
        <section className="bg-yellow-900/20 border border-yellow-500/50 rounded-2xl p-4">
          <h2 className="text-lg font-semibold text-yellow-400 mb-4">
            Near Misses ({nearMisses.length})
          </h2>
          <p className="text-yellow-300/70 text-sm mb-4">
            These markets came very close to triggering. They may trade soon.
          </p>

          <div className="grid gap-3">
            {nearMisses.slice(0, 5).map((c) => (
              <CandidateCard key={c.conditionId} candidate={c} highlight />
            ))}
          </div>
        </section>
      )}

      {/* Candidates */}
      {candidates && candidates.length > 0 && (
        <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
          <h2 className="text-lg font-semibold text-text-primary mb-4">
            Candidate Markets ({candidates.length})
          </h2>
          <p className="text-text-secondary text-sm mb-4">
            Markets that passed filters but are waiting for better entry conditions.
          </p>

          <div className="grid gap-3">
            {candidates.slice(0, 10).map((c) => (
              <CandidateCard key={c.conditionId} candidate={c} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function StatCard({
  label,
  value,
  subtext,
  highlight = false,
}: {
  label: string;
  value: string;
  subtext: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl p-4 ${
        highlight ? 'bg-yellow-900/20 border border-yellow-500/50' : 'bg-bg-secondary border border-border'
      }`}
    >
      <div className="text-text-secondary text-xs uppercase mb-1">{label}</div>
      <div className={`text-2xl font-bold ${highlight ? 'text-yellow-400' : 'text-text-primary'}`}>
        {value}
      </div>
      <div className="text-text-secondary text-xs mt-1">{subtext}</div>
    </div>
  );
}

function RejectionRow({ rejection }: { rejection: RejectionEvent }) {
  const time = new Date(rejection.timestamp);
  const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <tr className="border-b border-border/50 hover:bg-bg-tertiary">
      <td className="py-2 text-text-secondary">{timeStr}</td>
      <td className="py-2 text-text-primary truncate max-w-xs" title={rejection.question}>
        {rejection.question || rejection.tokenId.slice(0, 16) + '...'}
      </td>
      <td className="py-2 text-right text-text-primary">${rejection.price.toFixed(3)}</td>
      <td className="py-2 text-text-secondary text-xs">
        {Object.entries(rejection.rejectionValues || {})
          .map(([k, v]) => `${k}: ${v}`)
          .join(', ') || '-'}
      </td>
    </tr>
  );
}

function CandidateCard({ candidate, highlight = false }: { candidate: CandidateMarket; highlight?: boolean }) {
  const distancePercent = (candidate.distanceToThreshold * 100).toFixed(2);
  const updated = new Date(candidate.lastUpdated);
  const timeAgo = getTimeAgo(updated);

  return (
    <div
      className={`rounded-lg p-3 ${
        highlight ? 'bg-yellow-900/30 border border-yellow-500/30' : 'bg-bg-tertiary'
      }`}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 min-w-0">
          <div className="text-text-primary text-sm font-medium truncate" title={candidate.question}>
            {candidate.question || candidate.tokenId.slice(0, 24) + '...'}
          </div>
          <div className="text-text-secondary text-xs mt-1">
            Updated {timeAgo} | Evaluated {candidate.timesEvaluated}x
          </div>
        </div>
        <div className="text-right ml-4">
          <div className="text-text-primary font-mono">${candidate.currentPrice.toFixed(3)}</div>
          <div className={`text-xs ${highlight ? 'text-yellow-400' : 'text-text-secondary'}`}>
            {distancePercent}% away
          </div>
        </div>
      </div>

      <div className="flex gap-4 text-xs text-text-secondary">
        <span>Signal: {candidate.lastSignal}</span>
        {candidate.modelScore !== null && <span>Score: {(candidate.modelScore * 100).toFixed(0)}%</span>}
        <span>High: ${candidate.highestPriceSeen.toFixed(3)}</span>
      </div>
    </div>
  );
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
