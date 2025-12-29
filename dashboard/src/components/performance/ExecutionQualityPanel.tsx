/**
 * Execution Quality Panel
 *
 * Summarizes fill rates, slippage, and speed for recent orders.
 */
import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { EmptyState } from '../common/EmptyState';
import type { Order } from '../../types';

interface ExecutionQualityPanelProps {
  orders: Order[];
}

type SlippageBucket = {
  label: string;
  min: number;
  max: number;
};

const slippageBuckets: SlippageBucket[] = [
  { label: '<= -50', min: Number.NEGATIVE_INFINITY, max: -50 },
  { label: '-50 to 0', min: -50, max: 0 },
  { label: '0 to 50', min: 0, max: 50 },
  { label: '50 to 100', min: 50, max: 100 },
  { label: '100 to 200', min: 100, max: 200 },
  { label: '>= 200', min: 200, max: Number.POSITIVE_INFINITY },
];

export function ExecutionQualityPanel({ orders }: ExecutionQualityPanelProps) {
  const metrics = useMemo(() => {
    const total = orders.length;
    const filled = orders.filter((o) => o.status === 'filled');
    const partial = orders.filter((o) => o.status === 'partial');
    const cancelled = orders.filter((o) => o.status === 'cancelled');

    const filledOrPartialCount = filled.length + partial.length;
    const totalSize = orders.reduce((sum, o) => sum + (o.size || 0), 0);
    const filledSize = orders.reduce((sum, o) => sum + (o.filledSize || 0), 0);

    const fillRate = total > 0 ? (filledOrPartialCount / total) * 100 : 0;
    const cancelRate = total > 0 ? (cancelled.length / total) * 100 : 0;
    const fillRatio = totalSize > 0 ? (filledSize / totalSize) * 100 : 0;

    const slippageValues = filled
      .map((o) => o.slippage)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      .sort((a, b) => a - b);

    const avgSlippage = slippageValues.length
      ? slippageValues.reduce((sum, value) => sum + value, 0) / slippageValues.length
      : null;
    const medianSlippage = slippageValues.length
      ? slippageValues[Math.floor(slippageValues.length / 2)]
      : null;
    const slippageP90Index = slippageValues.length
      ? Math.max(0, Math.ceil(slippageValues.length * 0.9) - 1)
      : null;
    const p90Slippage = slippageP90Index !== null ? slippageValues[slippageP90Index] : null;

    const fillTimesMs = filled
      .map((order) => {
        const created = Date.parse(order.createdAt);
        const updated = Date.parse(order.updatedAt);
        if (Number.isNaN(created) || Number.isNaN(updated)) return null;
        return Math.max(0, updated - created);
      })
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      .sort((a, b) => a - b);

    const avgFillTimeMs = fillTimesMs.length
      ? fillTimesMs.reduce((sum, value) => sum + value, 0) / fillTimesMs.length
      : null;
    const fillP90Index = fillTimesMs.length
      ? Math.max(0, Math.ceil(fillTimesMs.length * 0.9) - 1)
      : null;
    const p90FillTimeMs = fillP90Index !== null ? fillTimesMs[fillP90Index] : null;

    const slippageSeries = slippageBuckets.map((bucket) => ({
      label: bucket.label,
      count: slippageValues.filter((value) => value > bucket.min && value <= bucket.max).length,
    }));

    return {
      total,
      cancelledCount: cancelled.length,
      filledOrPartialCount,
      fillRate,
      cancelRate,
      fillRatio,
      avgSlippage,
      medianSlippage,
      p90Slippage,
      avgFillTimeMs,
      p90FillTimeMs,
      slippageSeries,
    };
  }, [orders]);

  return (
    <section className="bg-bg-secondary rounded-lg p-4 border border-border">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Execution
          </div>
          <h3 className="text-lg font-semibold text-text-primary">Execution Quality</h3>
          <p className="text-text-secondary text-sm">
            Fill rate, slippage, and speed on recent orders.
          </p>
        </div>
        <div className="text-xs text-text-secondary">
          {metrics.total > 0 ? `${metrics.total} orders` : 'No orders'}
        </div>
      </div>

      {metrics.total === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="No execution data"
            description="Submit trades to see fill and slippage metrics."
          />
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
            <MetricTile
              label="Fill rate"
              value={`${metrics.fillRate.toFixed(1)}%`}
              subtext={`${metrics.filledOrPartialCount}/${metrics.total} orders`}
            />
            <MetricTile
              label="Fill ratio"
              value={`${metrics.fillRatio.toFixed(1)}%`}
              subtext="Filled size / submitted"
            />
            <MetricTile
              label="Cancel rate"
              value={`${metrics.cancelRate.toFixed(1)}%`}
              subtext={`${metrics.cancelledCount}/${metrics.total} cancelled`}
            />
            <MetricTile
              label="Avg slippage"
              value={formatBps(metrics.avgSlippage)}
              subtext={`Median ${formatBps(metrics.medianSlippage)} | P90 ${formatBps(metrics.p90Slippage)}`}
            />
            <MetricTile
              label="Fill speed"
              value={formatDuration(metrics.avgFillTimeMs)}
              subtext={`P90 ${formatDuration(metrics.p90FillTimeMs)}`}
            />
          </div>

          <div className="mt-6">
            <div className="text-xs uppercase tracking-wide text-text-secondary/70">
              Slippage Distribution (bps)
            </div>
            {metrics.slippageSeries.every((bucket) => bucket.count === 0) ? (
              <div className="text-sm text-text-secondary mt-3">No fill slippage captured yet.</div>
            ) : (
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics.slippageSeries} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                    <XAxis dataKey="label" stroke="#8b949e" fontSize={11} />
                    <YAxis stroke="#8b949e" fontSize={11} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#161b22',
                        border: '1px solid #30363d',
                        borderRadius: '8px',
                      }}
                      labelStyle={{ color: '#8b949e' }}
                    />
                    <Bar dataKey="count" fill="#58a6ff" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function MetricTile({ label, value, subtext }: { label: string; value: string; subtext: string }) {
  return (
    <div className="rounded-xl border border-border bg-bg-tertiary/50 p-3">
      <div className="text-[10px] uppercase tracking-wide text-text-secondary/70">{label}</div>
      <div className="text-lg font-semibold text-text-primary">{value}</div>
      <div className="text-xs text-text-secondary">{subtext}</div>
    </div>
  );
}

function formatBps(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'n/a';
  return `${value.toFixed(1)} bps`;
}

function formatDuration(valueMs: number | null): string {
  if (valueMs === null || Number.isNaN(valueMs)) return 'n/a';
  if (valueMs < 1000) return `${Math.round(valueMs)}ms`;
  const seconds = valueMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  const hours = minutes / 60;
  return `${hours.toFixed(1)}h`;
}
