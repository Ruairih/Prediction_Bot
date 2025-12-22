/**
 * Strategy Page
 * Strategy configuration and backtesting
 */
import { useState } from 'react';
import clsx from 'clsx';
import type { StrategyConfig, BacktestResult } from '../types';

// Mock data
const mockStrategy: StrategyConfig = {
  name: 'Momentum Edge',
  version: '1.2.0',
  enabled: true,
  parameters: [
    { key: 'priceThreshold', label: 'Price Threshold', type: 'number', value: 0.95, defaultValue: 0.95, min: 0.5, max: 0.99, step: 0.01, unit: '', description: 'Minimum price to trigger entry' },
    { key: 'minTradeSize', label: 'Min Trade Size', type: 'number', value: 50, defaultValue: 50, min: 10, max: 500, step: 10, unit: 'shares', description: 'Minimum trade size in shares' },
    { key: 'maxPositions', label: 'Max Positions', type: 'number', value: 5, defaultValue: 5, min: 1, max: 20, step: 1, description: 'Maximum concurrent positions' },
    { key: 'stopLoss', label: 'Stop Loss', type: 'number', value: 0.15, defaultValue: 0.15, min: 0.05, max: 0.50, step: 0.01, unit: '%', description: 'Stop loss percentage' },
  ],
  filters: {
    blockedCategories: ['Weather', 'Sports'],
    weatherFilterEnabled: true,
    minTradeSize: 50,
    maxTradeAge: 300,
    minTimeToExpiry: 6,
    maxPriceDeviation: 0.10,
  },
  lastModified: new Date().toISOString(),
};

const mockBacktests: BacktestResult[] = [
  {
    id: 'bt1',
    status: 'completed',
    period: { start: '2024-10-01', end: '2024-12-01' },
    trades: 45,
    winRate: 0.89,
    pnl: 125.50,
    sharpeRatio: 2.1,
    maxDrawdown: 8.5,
    equitySeries: [],
    createdAt: new Date(Date.now() - 86400000).toISOString(),
    completedAt: new Date(Date.now() - 86400000 + 60000).toISOString(),
  },
];

export function Strategy() {
  const [strategy, setStrategy] = useState<StrategyConfig>(mockStrategy);
  const [backtests] = useState<BacktestResult[]>(mockBacktests);
  const [hasChanges, setHasChanges] = useState(false);

  const handleToggle = () => {
    setStrategy({ ...strategy, enabled: !strategy.enabled });
    setHasChanges(true);
  };

  const handleParameterChange = (key: string, value: number | boolean | string) => {
    setStrategy({
      ...strategy,
      parameters: strategy.parameters.map((p) =>
        p.key === key ? { ...p, value } : p
      ),
    });
    setHasChanges(true);
  };

  const handleSave = () => {
    console.log('Saving strategy:', strategy);
    setHasChanges(false);
    // TODO: Implement API call
  };

  const handleRevert = () => {
    setStrategy(mockStrategy);
    setHasChanges(false);
  };

  const handleRunBacktest = () => {
    console.log('Running backtest...');
    // TODO: Implement backtest
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Strategy</h1>
        <p className="text-text-secondary">Configure your trading strategy parameters</p>
      </div>

      {/* Strategy Status Card */}
      <div
        data-testid="strategy-status"
        className="bg-bg-secondary rounded-lg p-4 border border-border"
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{strategy.name}</h3>
            <p className="text-sm text-text-secondary">Version {strategy.version}</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-text-secondary">
              {strategy.enabled ? 'Enabled' : 'Disabled'}
            </span>
            <button
              role="switch"
              aria-checked={strategy.enabled}
              aria-label="Enable strategy"
              onClick={handleToggle}
              className={clsx(
                'relative w-12 h-6 rounded-full transition-colors',
                strategy.enabled ? 'bg-accent-green' : 'bg-bg-tertiary'
              )}
            >
              <span
                className={clsx(
                  'absolute top-1 w-4 h-4 bg-white rounded-full transition-transform',
                  strategy.enabled ? 'left-7' : 'left-1'
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
            {strategy.parameters.map((param) => (
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
                {strategy.filters.blockedCategories.map((cat) => (
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
              <span className={strategy.filters.weatherFilterEnabled ? 'text-accent-green' : 'text-accent-red'}>
                {strategy.filters.weatherFilterEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Min Trade Size</span>
              <span className="text-text-primary">{strategy.filters.minTradeSize} shares</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Max Trade Age</span>
              <span className="text-text-primary">{strategy.filters.maxTradeAge}s</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Min Time to Expiry</span>
              <span className="text-text-primary">{strategy.filters.minTimeToExpiry}h</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Max Price Deviation</span>
              <span className="text-text-primary">{(strategy.filters.maxPriceDeviation * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Backtesting Section */}
      <div data-testid="backtest-section" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">Backtesting</h3>
          <button
            onClick={handleRunBacktest}
            className="px-4 py-2 bg-accent-blue text-white rounded-lg hover:bg-accent-blue/80 transition-colors"
          >
            Run Backtest
          </button>
        </div>

        <div data-testid="backtest-history">
          <h4 className="text-sm font-medium text-text-secondary mb-2">Recent Backtests</h4>
          {backtests.length === 0 ? (
            <p className="text-text-secondary text-sm">No backtests run yet</p>
          ) : (
            <div className="space-y-2">
              {backtests.map((bt) => (
                <div
                  key={bt.id}
                  className="flex items-center justify-between p-3 bg-bg-tertiary rounded-lg"
                >
                  <div>
                    <div className="text-sm text-text-primary">
                      {bt.period.start} to {bt.period.end}
                    </div>
                    <div className="text-xs text-text-secondary">
                      {bt.trades} trades • {(bt.winRate * 100).toFixed(0)}% win rate
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={bt.pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                      {bt.pnl >= 0 ? '+' : ''}${bt.pnl.toFixed(2)}
                    </div>
                    <div className="text-xs text-text-secondary">
                      Sharpe: {bt.sharpeRatio.toFixed(2)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
