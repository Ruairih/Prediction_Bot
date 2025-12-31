/**
 * Pipeline Page
 *
 * Shows visibility into the trading pipeline:
 * - Rejection funnel (why markets are filtered)
 * - Candidate markets (close to threshold)
 * - Near-misses (almost triggered)
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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

const stageInfo: Record<RejectionStage, { label: string; description: string }> = {
  threshold: {
    label: 'Below threshold',
    description: 'Price did not reach the strategy entry threshold.',
  },
  duplicate: {
    label: 'Duplicate trigger',
    description: 'Market already triggered recently; duplicate ignored.',
  },
  g1_trade_age: {
    label: 'Stale trade data',
    description: 'Last trade data older than max age.',
  },
  g5_orderbook: {
    label: 'Orderbook mismatch',
    description: 'Orderbook price deviates from the trigger price.',
  },
  g6_weather: {
    label: 'Weather filter',
    description: 'Weather-related markets are filtered.',
  },
  time_to_end: {
    label: 'Too close to expiry',
    description: 'Market ends before minimum holding window.',
  },
  trade_size: {
    label: 'Trade size too small',
    description: 'Latest trade size below minimum.',
  },
  category: {
    label: 'Blocked category',
    description: 'Category filtered by strategy settings.',
  },
  manual_block: {
    label: 'Manual block',
    description: 'Market blocked by operator.',
  },
  max_positions: {
    label: 'Position cap reached',
    description: 'Max concurrent positions reached.',
  },
  strategy_hold: {
    label: 'Strategy hold',
    description: 'Strategy evaluated but chose HOLD.',
  },
  strategy_ignore: {
    label: 'Strategy ignore',
    description: 'Strategy ignored this market.',
  },
};

const stageGroups: Array<{ title: string; stages: RejectionStage[] }> = [
  {
    title: 'Pre-strategy filters',
    stages: [
      'threshold',
      'duplicate',
      'g1_trade_age',
      'g5_orderbook',
      'g6_weather',
      'time_to_end',
      'trade_size',
      'category',
      'manual_block',
      'max_positions',
    ],
  },
  {
    title: 'Strategy decisions',
    stages: ['strategy_hold', 'strategy_ignore'],
  },
];

const CANDIDATE_DISPLAY_LIMIT = 20;
const CANDIDATE_FETCH_LIMIT = 80;
const REJECTION_SAMPLE_LIMIT = 80;

export function Pipeline() {
  const [selectedStage, setSelectedStage] = useState<RejectionStage | null>(null);
  const [timeWindow, setTimeWindow] = useState(60);
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidateStatus, setCandidateStatus] = useState<'all' | 'triggered' | 'very_close' | 'watching'>('all');
  const [candidateSort, setCandidateSort] = useState<'distance' | 'score' | 'recent'>('distance');

  const { data: funnel, isLoading: funnelLoading, error: funnelError } = usePipelineFunnel(timeWindow);
  const { data: rejections } = usePipelineRejections(REJECTION_SAMPLE_LIMIT, selectedStage ?? undefined);
  const { data: candidates } = usePipelineCandidates(CANDIDATE_FETCH_LIMIT, candidateSort);
  const { data: nearMisses } = useNearMisses(0.02);

  const filteredCandidates = useMemo(() => {
    const base = candidates ?? [];
    const search = candidateSearch.trim().toLowerCase();

    return base.filter((candidate) => {
      if (candidateStatus !== 'all') {
        const status = candidate.statusLabel.toLowerCase();
        if (candidateStatus === 'triggered' && !status.includes('triggered')) return false;
        if (candidateStatus === 'very_close' && !status.includes('very close')) return false;
        if (candidateStatus === 'watching' && !status.includes('watching')) return false;
      }

      if (search) {
        const haystack = `${candidate.question} ${candidate.conditionId} ${candidate.tokenId}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }

      return true;
    });
  }, [candidates, candidateSearch, candidateStatus]);

  const visibleCandidates = filteredCandidates.slice(0, CANDIDATE_DISPLAY_LIMIT);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Signal Flow
          </div>
          <h1 className="text-3xl font-semibold text-text-primary">Pipeline</h1>
          <p className="text-text-secondary">
            Track where markets drop off and why the strategy holds.
          </p>
        </div>

        {/* Time window selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-secondary">Lookback</span>
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
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Rejections"
            value={funnel.totalRejections.toLocaleString()}
            subtext={`Last ${timeWindow}m`}
          />
          <StatCard
            label="Active Candidates"
            value={funnel.candidateCount.toString()}
            subtext="Markets in pipeline"
          />
          <StatCard
            label="Triggered but Held"
            value={funnel.nearMissCount.toString()}
            subtext="Price at or above threshold"
            highlight={funnel.nearMissCount > 0}
          />
          <StatCard
            label="Top Rejection Stage"
            value={funnel.funnel[0]?.label ?? 'N/A'}
            subtext={`${funnel.funnel[0]?.count ?? 0} (${funnel.funnel[0]?.percentage.toFixed(1) ?? 0}%)`}
          />
        </div>
      )}

      {/* Rejection Funnel */}
      <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Rejection Funnel</h2>
            <p className="text-sm text-text-secondary">
              Click a stage to filter recent samples. Counts reflect the selected lookback window.
            </p>
          </div>
          <div className="text-xs text-text-secondary">
            Detailed rejections are sampled to conserve memory.
          </div>
        </div>

        {funnelLoading ? (
          <div className="text-center py-8 text-text-secondary">Loading...</div>
        ) : !funnel ? (
          <EmptyState title="No data" description="Start the bot to see pipeline data" />
        ) : (
          <div className="space-y-2">
            {funnel.funnel
              .filter((item) => item.count > 0)
              .map((item) => (
                <button
                  key={item.stage}
                  onClick={() => setSelectedStage(selectedStage === item.stage ? null : item.stage)}
                  aria-pressed={selectedStage === item.stage}
                  aria-label={`${item.label}: ${item.count} rejections (${item.percentage.toFixed(1)}%)`}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg transition-colors ${
                    selectedStage === item.stage
                      ? 'bg-bg-tertiary ring-1 ring-accent-primary'
                      : 'hover:bg-bg-tertiary'
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full ${stageColors[item.stage]}`} aria-hidden="true" />
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

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {stageGroups.map((group) => (
            <div key={group.title} className="rounded-xl border border-border bg-bg-tertiary/60 p-3">
              <div className="text-xs uppercase tracking-wide text-text-secondary">{group.title}</div>
              <div className="mt-3 space-y-2">
                {group.stages.map((stage) => (
                  <div key={stage} className="flex items-start gap-2">
                    <span className={`mt-1 h-2 w-2 rounded-full ${stageColors[stage]}`} aria-hidden="true" />
                    <div>
                      <div className="text-sm text-text-primary">{stageInfo[stage].label}</div>
                      <div className="text-xs text-text-secondary">{stageInfo[stage].description}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Rejections */}
      <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Recent Rejections</h2>
            <p className="text-sm text-text-secondary">
              {selectedStage ? stageInfo[selectedStage].description : 'Sampled rejections across all stages.'}
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <label htmlFor="stage-filter" className="text-xs text-text-secondary">
              Stage
            </label>
            <select
              id="stage-filter"
              value={selectedStage ?? 'all'}
              onChange={(event) => {
                const next = event.target.value;
                setSelectedStage(next === 'all' ? null : (next as RejectionStage));
              }}
              className="rounded-lg border border-border bg-bg-tertiary px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
            >
              <option value="all">All stages</option>
              {stageGroups.flatMap((group) => group.stages).map((stage) => (
                <option key={stage} value={stage}>
                  {stageInfo[stage].label}
                </option>
              ))}
            </select>
            {selectedStage && (
              <button
                onClick={() => setSelectedStage(null)}
                className="text-text-secondary hover:text-text-primary text-sm"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {rejections && rejections.length > 0 ? (
          /* Horizontal scroll wrapper for mobile */
          <div className="overflow-x-auto -webkit-overflow-scrolling-touch">
            <table className="w-full min-w-[700px] text-sm" aria-label="Recent rejections">
              <caption className="sr-only">
                Recent pipeline rejections showing time, stage, market, price, key data, and rejection reason
              </caption>
              <thead>
                <tr className="text-left text-text-secondary border-b border-border">
                  <th scope="col" className="pb-2 font-medium">Time</th>
                  <th scope="col" className="pb-2 font-medium">Stage</th>
                  <th scope="col" className="pb-2 font-medium">Market</th>
                  <th scope="col" className="pb-2 font-medium text-right">Price</th>
                  <th scope="col" className="pb-2 font-medium">Key Data</th>
                  <th scope="col" className="pb-2 font-medium">Why Rejected</th>
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
            description={
              selectedStage
                ? `No ${stageInfo[selectedStage].label.toLowerCase()} samples recorded yet.`
                : 'No rejection samples recorded yet.'
            }
          />
        )}
      </section>

      {/* Triggered but Held - markets that hit threshold but strategy didn't trade */}
      {nearMisses && nearMisses.length > 0 && (
        <section className="bg-yellow-900/20 border border-yellow-500/50 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-yellow-400">
                Triggered but Held ({nearMisses.length})
              </h2>
              <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded">
                Price at or above threshold
              </span>
            </div>
            {nearMisses.length > 10 && (
              <span className="text-yellow-300/50 text-xs">
                Showing 10 of {nearMisses.length}
              </span>
            )}
          </div>
          <p className="text-yellow-300/70 text-sm mb-4">
            These markets reached the entry threshold but the strategy returned HOLD or WATCHLIST.
            Review the last signal reason to understand the hold.
          </p>

          <div className="grid gap-3 max-h-[600px] overflow-y-auto">
            {nearMisses.slice(0, 10).map((c) => (
              <CandidateCard key={c.conditionId} candidate={c} highlight />
            ))}
          </div>
          {nearMisses.length > 10 && (
            <div className="mt-3 text-center text-yellow-300/50 text-sm">
              {nearMisses.length - 10} more held triggers not shown
            </div>
          )}
        </section>
      )}

      {/* Candidates - all tracked markets (may include those above and below threshold) */}
      {candidates && (
        <section className="bg-bg-secondary rounded-2xl p-4 border border-border">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-text-primary">
                Candidate Watchlist ({candidates.length})
              </h2>
              <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">
                Being monitored
              </span>
            </div>
            <span className="text-text-secondary text-xs">
              Showing {Math.min(visibleCandidates.length, filteredCandidates.length)} of {filteredCandidates.length}
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <div className="flex items-center gap-2">
              <label htmlFor="candidate-sort" className="text-xs text-text-secondary">
                Sort
              </label>
              <select
                id="candidate-sort"
                value={candidateSort}
                onChange={(event) => setCandidateSort(event.target.value as typeof candidateSort)}
                className="rounded-full border border-border bg-bg-tertiary px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
              >
                <option value="distance">Closest to threshold</option>
                <option value="score">Highest model score</option>
                <option value="recent">Most recent update</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <label htmlFor="candidate-status" className="text-xs text-text-secondary">
                Status
              </label>
              <select
                id="candidate-status"
                value={candidateStatus}
                onChange={(event) => setCandidateStatus(event.target.value as typeof candidateStatus)}
                className="rounded-full border border-border bg-bg-tertiary px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
              >
                <option value="all">All</option>
                <option value="triggered">Triggered (Held)</option>
                <option value="very_close">Very Close</option>
                <option value="watching">Watching</option>
              </select>
            </div>

            <div className="flex-1 min-w-[220px]">
              <input
                type="search"
                value={candidateSearch}
                onChange={(event) => setCandidateSearch(event.target.value)}
                placeholder="Search candidates or condition id"
                className="w-full rounded-full border border-border bg-bg-tertiary px-3 py-1.5 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-blue"
              />
            </div>
          </div>

          <p className="text-text-secondary text-sm mt-3 mb-4">
            Status guide: <strong>Triggered (Held)</strong> means price reached threshold but the strategy held.
            <strong> Very Close</strong> is within 2% of threshold, and <strong>Watching</strong> is farther away.
          </p>

          {filteredCandidates.length > 0 ? (
            <>
              <div className="grid gap-3 max-h-[800px] overflow-y-auto">
                {visibleCandidates.map((c) => (
                  <CandidateCard key={c.conditionId} candidate={c} />
                ))}
              </div>
              {filteredCandidates.length > CANDIDATE_DISPLAY_LIMIT && (
                <div className="mt-3 text-center text-text-secondary text-sm">
                  {filteredCandidates.length - CANDIDATE_DISPLAY_LIMIT} more candidates not shown
                </div>
              )}
            </>
          ) : (
            <EmptyState
              title="No candidates found"
              description="No markets match the current filters."
            />
          )}
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

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return null;

  const isYes = outcome.toLowerCase() === 'yes';
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
        isYes
          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
          : 'bg-red-500/20 text-red-400 border border-red-500/30'
      }`}
    >
      {isYes ? 'YES' : 'NO'}
    </span>
  );
}

function StageBadge({ stage }: { stage: RejectionStage }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg-tertiary px-2 py-0.5 text-xs text-text-primary"
      title={stageInfo[stage].description}
    >
      <span className={`h-2 w-2 rounded-full ${stageColors[stage]}`} aria-hidden="true" />
      {stageInfo[stage].label}
    </span>
  );
}

function StatusBadge({ statusLabel }: { statusLabel: string }) {
  let colorClass = 'bg-blue-500/20 text-blue-400 border border-blue-500/30';

  if (statusLabel.includes('Triggered') || statusLabel.includes('Held')) {
    colorClass = 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30';
  } else if (statusLabel.includes('Very Close')) {
    colorClass = 'bg-orange-500/20 text-orange-400 border border-orange-500/30';
  }

  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${colorClass}`}>
      {statusLabel}
    </span>
  );
}

function CandidateMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[110px]">
      <div className="text-[10px] uppercase tracking-wide text-text-secondary/70">{label}</div>
      <div className="text-xs text-text-primary">{value}</div>
    </div>
  );
}

function RejectionRow({ rejection }: { rejection: RejectionEvent }) {
  const time = new Date(rejection.timestamp);
  const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <tr className="border-b border-border/50 hover:bg-bg-tertiary">
      <td className="py-2 text-text-secondary">{timeStr}</td>
      <td className="py-2">
        <StageBadge stage={rejection.stage} />
      </td>
      <td className="py-2">
        <div className="flex items-center gap-2">
          <OutcomeBadge outcome={rejection.outcome} />
          {rejection.conditionId ? (
            <Link
              to={`/markets?conditionId=${encodeURIComponent(rejection.conditionId)}`}
              className="text-text-primary truncate max-w-xs hover:text-accent-blue transition-colors"
              title={rejection.question}
            >
              {rejection.question || rejection.tokenId.slice(0, 16) + '...'}
            </Link>
          ) : (
            <span className="text-text-primary truncate max-w-xs" title={rejection.question}>
              {rejection.question || rejection.tokenId.slice(0, 16) + '...'}
            </span>
          )}
        </div>
      </td>
      <td className="py-2 text-right text-text-primary">${rejection.price.toFixed(3)}</td>
      <td className="py-2 text-text-secondary text-xs">
        <span title={JSON.stringify(rejection.rejectionValues, null, 2)}>
          {formatRejectionMetric(rejection)}
        </span>
      </td>
      <td className="py-2 text-text-secondary text-xs max-w-sm">
        <span title={JSON.stringify(rejection.rejectionValues, null, 2)}>
          {rejection.rejectionReason || '-'}
        </span>
      </td>
    </tr>
  );
}

function CandidateCard({ candidate, highlight = false }: { candidate: CandidateMarket; highlight?: boolean }) {
  const updated = new Date(candidate.lastUpdated);
  const timeAgo = getTimeAgo(updated);

  const distancePercent = Math.abs(candidate.distanceToThreshold * 100).toFixed(2);
  const distanceLabel = candidate.distanceToThreshold <= 0
    ? `${distancePercent}% above threshold`
    : `${distancePercent}% below threshold`;
  const scoreLabel = candidate.modelScore !== null ? `${(candidate.modelScore * 100).toFixed(0)}%` : '-';
  const tradeSizeLabel = formatNullableNumber(candidate.tradeSize, 0);
  const tradeAgeLabel = formatDurationSeconds(candidate.tradeAgeSeconds);
  const timeToEndLabel = formatDurationHours(candidate.timeToEndHours);

  return (
    <div
      className={`rounded-lg p-3 ${
        highlight ? 'bg-yellow-900/30 border border-yellow-500/30' : 'bg-bg-tertiary'
      }`}
    >
      <div className="flex justify-between items-start gap-4 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <OutcomeBadge outcome={candidate.outcome} />
            <StatusBadge statusLabel={candidate.statusLabel} />
          </div>
          <Link
            to={`/markets?conditionId=${encodeURIComponent(candidate.conditionId)}`}
            className="text-text-primary text-sm font-medium truncate block hover:text-accent-blue transition-colors"
            title={candidate.question}
          >
            {candidate.question || candidate.tokenId.slice(0, 24) + '...'}
          </Link>
          <div className="text-text-secondary text-xs mt-1">
            Updated {timeAgo} | Evaluated {candidate.timesEvaluated}x
          </div>
        </div>
        <div className="text-right ml-4">
          <div className="text-text-primary font-mono">${candidate.currentPrice.toFixed(3)}</div>
          <div className={`text-xs ${candidate.isAboveThreshold ? 'text-green-400' : 'text-text-secondary'}`}>
            {distanceLabel}
          </div>
          <div className="text-xs text-text-secondary">Threshold {formatPrice(candidate.threshold)}</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <CandidateMetric label="Signal" value={candidate.lastSignal} />
        <CandidateMetric label="Score" value={scoreLabel} />
        <CandidateMetric label="Time to end" value={timeToEndLabel} />
        <CandidateMetric label="Trade size" value={tradeSizeLabel} />
        <CandidateMetric label="Trade age" value={tradeAgeLabel} />
        <CandidateMetric label="High" value={formatPrice(candidate.highestPriceSeen)} />
      </div>

      {candidate.lastSignalReason && (
        <div className="mt-2 text-xs text-text-secondary italic">
          Reason: {candidate.lastSignalReason}
        </div>
      )}

      <div className="mt-2 pt-2 border-t border-border/50">
        <Link
          to={`/markets?conditionId=${encodeURIComponent(candidate.conditionId)}`}
          className="text-xs text-accent-blue hover:text-accent-blue/80 transition-colors"
        >
          View Market Details &rarr;
        </Link>
      </div>
    </div>
  );
}

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `$${value.toFixed(3)}`;
}

function formatNullableNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
}

function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function formatDurationHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return '-';
  if (hours <= 0) return '0h';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function formatRejectionMetric(rejection: RejectionEvent): string {
  const values = rejection.rejectionValues ?? {};
  const asNumber = (value: unknown): number | null => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
      return Number(value);
    }
    return null;
  };

  switch (rejection.stage) {
    case 'threshold': {
      const price = asNumber(values.price) ?? rejection.price;
      const threshold = asNumber(values.threshold);
      if (price !== null && threshold !== null) {
        return `${price.toFixed(3)} vs ${threshold.toFixed(3)}`;
      }
      return `${rejection.price.toFixed(3)}`;
    }
    case 'duplicate':
      return 'Already triggered';
    case 'g1_trade_age': {
      const ageSeconds = asNumber(values.age_seconds) ?? rejection.tradeAgeSeconds;
      const maxAge = asNumber(values.max_age);
      if (ageSeconds !== null && maxAge !== null) {
        return `${Math.round(ageSeconds)}s > ${Math.round(maxAge)}s`;
      }
      if (ageSeconds !== null) {
        return `${Math.round(ageSeconds)}s old`;
      }
      return '-';
    }
    case 'g5_orderbook': {
      const deviation = asNumber(values.deviation_pct);
      const orderbook = asNumber(values.orderbook_price);
      const trigger = asNumber(values.trigger_price);
      if (deviation !== null) return `${deviation.toFixed(2)}% dev`;
      if (orderbook !== null && trigger !== null) return `${orderbook.toFixed(3)} vs ${trigger.toFixed(3)}`;
      return '-';
    }
    case 'g6_weather':
      return 'Weather filter';
    case 'time_to_end': {
      const hoursRemaining = asNumber(values.hours_remaining);
      const minHours = asNumber(values.min_hours);
      if (hoursRemaining !== null && minHours !== null) {
        return `${formatDurationHours(hoursRemaining)} < ${formatDurationHours(minHours)}`;
      }
      if (hoursRemaining !== null) {
        return `${formatDurationHours(hoursRemaining)} left`;
      }
      return '-';
    }
    case 'trade_size': {
      const size = asNumber(values.size) ?? rejection.tradeSize;
      const minSize = asNumber(values.min_size);
      if (size !== null && minSize !== null) {
        return `${size.toFixed(0)} < ${minSize.toFixed(0)}`;
      }
      if (size !== null) {
        return `${size.toFixed(0)} size`;
      }
      return '-';
    }
    case 'category':
      return typeof values.category === 'string' && values.category ? values.category : 'Blocked';
    case 'manual_block':
      return typeof values.reason === 'string' && values.reason ? values.reason : 'Manual block';
    case 'max_positions': {
      const current = asNumber(values.current);
      const max = asNumber(values.max);
      if (current !== null && max !== null) {
        return `${current}/${max}`;
      }
      return 'Position cap';
    }
    case 'strategy_hold':
    case 'strategy_ignore':
      return typeof values.reason === 'string' && values.reason ? values.reason : 'Strategy decision';
    default:
      return '-';
  }
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
