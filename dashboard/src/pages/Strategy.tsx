/**
 * Strategy Page
 * Strategy configuration and backtesting
 */
import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { useStrategy, useDecisions } from '../hooks/useDashboardData';
import { updateRiskLimits, pauseTrading, resumeTrading } from '../api/dashboard';
import type { StrategyConfig, Signal, RiskLimits } from '../types';

export function Strategy() {
  const { data: strategyData, isLoading, error, refetch } = useStrategy();
  const { data: decisionsData } = useDecisions(150);
  const [strategy, setStrategy] = useState<StrategyConfig | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (strategyData) {
      setStrategy(strategyData);
      setHasChanges(false);
    }
  }, [strategyData]);

  const decisions = decisionsData ?? [];

  const handleToggle = async () => {
    if (!strategy) return;
    if (strategy.enabled) {
      await pauseTrading('strategy_toggle');
    } else {
      await resumeTrading();
    }
    await refetch();
  };

  const handleParameterChange = (key: string, value: number | boolean | string) => {
    if (!strategy) return;
    setStrategy({
      ...strategy,
      parameters: strategy.parameters.map((p) =>
        p.key === key ? { ...p, value } : p
      ),
    });
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!strategy) return;
    const payload: Partial<RiskLimits> = {};
    strategy.parameters.forEach((param) => {
      if (param.key === 'price_threshold') payload.priceThreshold = param.value as number;
      if (param.key === 'position_size') payload.maxPositionSize = param.value as number;
      if (param.key === 'max_positions') payload.maxPositions = param.value as number;
      if (param.key === 'max_price_deviation') payload.maxPriceDeviation = param.value as number;
      if (param.key === 'stop_loss') payload.stopLoss = param.value as number;
      if (param.key === 'profit_target') payload.profitTarget = param.value as number;
      if (param.key === 'min_hold_days') payload.minHoldDays = param.value as number;
    });
    await updateRiskLimits(payload);
    await refetch();
    setHasChanges(false);
  };

  const handleRevert = () => {
    if (strategyData) {
      setStrategy(strategyData);
    }
    setHasChanges(false);
  };

  const handleRunBacktest = () => {
    console.log('Backtesting not configured');
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Strategy</h1>
        <p className="text-text-secondary">Configure your trading strategy parameters</p>
      </div>

      {isLoading && <div className="text-sm text-text-secondary">Loading strategy configuration...</div>}
      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">Unable to load strategy configuration.</p>
        </div>
      )}

      {/* Strategy Status Card */}
      <div
        data-testid="strategy-status"
        className="bg-bg-secondary rounded-lg p-4 border border-border"
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{strategy?.name ?? 'Strategy'}</h3>
            <p className="text-sm text-text-secondary">Version {strategy?.version ?? 'n/a'}</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-text-secondary">
              {strategy?.enabled ? 'Enabled' : 'Disabled'}
            </span>
            <button
              role="switch"
              aria-checked={strategy?.enabled ?? false}
              aria-label="Enable strategy"
              onClick={handleToggle}
              className={clsx(
                'relative w-12 h-6 rounded-full transition-colors',
                strategy?.enabled ? 'bg-accent-green' : 'bg-bg-tertiary'
              )}
            >
              <span
                className={clsx(
                  'absolute top-1 w-4 h-4 bg-white rounded-full transition-transform',
                  strategy?.enabled ? 'left-7' : 'left-1'
                )}
              />
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Strategy Parameters */}
        <div
          data-testid="strategy-parameters"
          className="bg-bg-secondary rounded-lg p-4 border border-border"
        >
          <h3 className="text-lg font-semibold mb-4 text-text-primary">Parameters</h3>
          <div className="space-y-4">
            {(strategy?.parameters ?? []).map((param) => (
              <div key={param.key}>
                <label className="block text-sm text-text-secondary mb-1">
                  {param.label}
                  {param.unit && <span className="text-text-secondary/60 ml-1">({param.unit})</span>}
                </label>
                <input
                  type="number"
                  value={param.value as number}
                  onChange={(e) => handleParameterChange(param.key, parseFloat(e.target.value))}
                  min={param.min}
                  max={param.max}
                  step={param.step}
                  className="w-full bg-bg-tertiary border border-border rounded-lg px-3 py-2 text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
                />
                {param.description && (
                  <p className="text-xs text-text-secondary mt-1">{param.description}</p>
                )}
              </div>
            ))}
          </div>

          <div className="flex gap-2 mt-6">
            <button
              onClick={handleSave}
              disabled={!hasChanges}
              className={clsx(
                'flex-1 py-2 rounded-lg font-medium transition-colors',
                hasChanges
                  ? 'bg-accent-blue text-white hover:bg-accent-blue/80'
                  : 'bg-bg-tertiary text-text-secondary cursor-not-allowed'
              )}
            >
              Save Changes
            </button>
            <button
              onClick={handleRevert}
              disabled={!hasChanges}
              className={clsx(
                'flex-1 py-2 rounded-lg font-medium transition-colors',
                hasChanges
                  ? 'bg-bg-tertiary text-text-primary hover:bg-bg-tertiary/80'
                  : 'bg-bg-tertiary text-text-secondary cursor-not-allowed'
              )}
            >
              Revert
            </button>
          </div>
        </div>

        {/* Filter Configuration */}
        <div
          data-testid="filter-config"
          className="bg-bg-secondary rounded-lg p-4 border border-border"
        >
          <h3 className="text-lg font-semibold mb-4 text-text-primary">Filters</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1">Blocked Categories</label>
              <div className="flex flex-wrap gap-2">
                {(strategy?.filters.blockedCategories ?? []).map((cat) => (
                  <span
                    key={cat}
                    className="px-2 py-1 bg-accent-red/20 text-accent-red text-xs rounded"
                  >
                    {cat}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Weather Filter</span>
              <span className={strategy?.filters.weatherFilterEnabled ? 'text-accent-green' : 'text-accent-red'}>
                {strategy?.filters.weatherFilterEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Min Trade Size</span>
              <span className="text-text-primary">{strategy?.filters.minTradeSize ?? 0}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Max Trade Age</span>
              <span className="text-text-primary">{strategy?.filters.maxTradeAge ?? 0}s</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Min Time to Expiry</span>
              <span className="text-text-primary">{strategy?.filters.minTimeToExpiry ?? 0}h</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Max Price Deviation</span>
              <span className="text-text-primary">{((strategy?.filters.maxPriceDeviation ?? 0) * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Decision Log */}
      <div data-testid="decision-log" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">Decision Log</h3>
          <button
            onClick={handleRunBacktest}
            className="px-4 py-2 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
          >
            Export
          </button>
        </div>
        {decisions.length === 0 ? (
          <p className="text-text-secondary text-sm">No decisions recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {decisions.slice(0, 15).map((decision: Signal) => (
              <div key={decision.id} className="flex items-center justify-between p-3 bg-bg-tertiary rounded-lg">
                <div className="min-w-0">
                  <div className="text-sm text-text-primary truncate">{decision.question}</div>
                  <div className="text-xs text-text-secondary">
                    {decision.decision.toUpperCase()} • {decision.modelScore ?? 'n/a'}
                  </div>
                </div>
                <div className="text-xs text-text-secondary">{new Date(decision.timestamp).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
