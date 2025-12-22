/**
 * Risk Page
 * Risk metrics and exposure management
 */
import { useState } from 'react';
import clsx from 'clsx';
import type { ExposureMetric, ExposureByCategory, RiskLimits, RiskAlert } from '../types';

// Mock data
const mockExposure: ExposureMetric = {
  currentExposure: 83.25,
  maxExposure: 500,
  exposurePercent: 16.65,
  leverage: 1.0,
};

const mockExposureByCategory: ExposureByCategory[] = [
  { category: 'Crypto', exposure: 45.50, positionCount: 2, pnl: 7.50, riskLevel: 'medium' },
  { category: 'Politics', exposure: 22.75, positionCount: 1, pnl: -1.20, riskLevel: 'low' },
  { category: 'Economics', exposure: 15.00, positionCount: 1, pnl: 2.30, riskLevel: 'low' },
];

const mockLimits: RiskLimits = {
  maxPositionSize: 100,
  maxTotalExposure: 500,
  maxPositions: 10,
  minBalanceReserve: 50,
  priceThreshold: 0.95,
  stopLoss: 0.15,
  profitTarget: 0.20,
  minHoldDays: 1,
};

const mockAlerts: RiskAlert[] = [
  {
    id: 'alert1',
    type: 'exposure',
    threshold: 0.50,
    currentValue: 0.17,
    message: 'Exposure approaching 20% of max limit',
    triggeredAt: new Date(Date.now() - 3600000).toISOString(),
    acknowledged: false,
  },
];

const correlationData = [
  ['Crypto', 'Politics', 0.15],
  ['Crypto', 'Economics', 0.45],
  ['Politics', 'Economics', 0.32],
] as const;

export function Risk() {
  const [exposure] = useState<ExposureMetric>(mockExposure);
  const [exposureByCategory] = useState<ExposureByCategory[]>(mockExposureByCategory);
  const [limits, setLimits] = useState<RiskLimits>(mockLimits);
  const [alerts, setAlerts] = useState<RiskAlert[]>(mockAlerts);
  const [showLimitModal, setShowLimitModal] = useState(false);
  const [editingLimits, setEditingLimits] = useState<RiskLimits | null>(null);

  const openLimitModal = () => {
    setEditingLimits({ ...limits });
    setShowLimitModal(true);
  };

  const saveLimits = () => {
    if (editingLimits) {
      setLimits(editingLimits);
    }
    setShowLimitModal(false);
    setEditingLimits(null);
  };

  const cancelLimitEdit = () => {
    setShowLimitModal(false);
    setEditingLimits(null);
  };

  const acknowledgeAlert = (id: string) => {
    setAlerts(alerts.filter((a) => a.id !== id));
  };

  const riskLevelColors = {
    low: 'bg-accent-green/20 text-accent-green',
    medium: 'bg-accent-yellow/20 text-accent-yellow',
    high: 'bg-accent-red/20 text-accent-red',
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Risk</h1>
        <p className="text-text-secondary">Monitor and manage your risk exposure</p>
      </div>

      {/* Exposure Summary */}
      <div data-testid="exposure-summary" className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-1">Current Exposure</div>
          <div className="text-2xl font-bold text-text-primary">
            ${exposure.currentExposure.toFixed(2)}
          </div>
        </div>

        <div className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-1">Max Exposure</div>
          <div className="text-2xl font-bold text-text-primary">
            ${exposure.maxExposure.toFixed(2)}
          </div>
        </div>

        <div className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-1">Exposure %</div>
          <div className="text-2xl font-bold text-text-primary">
            {exposure.exposurePercent.toFixed(1)}%
          </div>
        </div>

        <div className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-1">Leverage</div>
          <div className="text-2xl font-bold text-text-primary">
            {exposure.leverage.toFixed(1)}x
          </div>
        </div>
      </div>

      {/* Exposure Gauge */}
      <div data-testid="exposure-gauge" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Exposure Level</h3>
        <div className="relative h-4 bg-bg-tertiary rounded-full overflow-hidden">
          <div
            role="progressbar"
            aria-valuenow={exposure.exposurePercent}
            aria-valuemin={0}
            aria-valuemax={100}
            className={clsx(
              'absolute h-full rounded-full transition-all',
              exposure.exposurePercent < 50 ? 'bg-accent-green' :
              exposure.exposurePercent < 80 ? 'bg-accent-yellow' : 'bg-accent-red'
            )}
            style={{ width: `${exposure.exposurePercent}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-text-secondary mt-2">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Limits */}
        <div data-testid="risk-limits" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Risk Limits</h3>
            <button
              onClick={openLimitModal}
              className="px-3 py-1 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80 transition-colors text-sm"
            >
              Edit Limits
            </button>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-text-secondary">Max Position Size</span>
              <span className="text-text-primary">${limits.maxPositionSize}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Max Total Exposure</span>
              <span className="text-text-primary">${limits.maxTotalExposure}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Max Positions</span>
              <span className="text-text-primary">{limits.maxPositions}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Stop Loss</span>
              <span className="text-text-primary">{(limits.stopLoss * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Profit Target</span>
              <span className="text-text-primary">{(limits.profitTarget * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>

        {/* Risk Alerts */}
        <div data-testid="risk-alerts" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <h3 className="text-lg font-semibold mb-4 text-text-primary">Active Alerts</h3>
          {alerts.length === 0 ? (
            <p className="text-text-secondary text-sm">No active alerts</p>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  data-testid="risk-alert-item"
                  className="flex items-center justify-between p-3 bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg"
                >
                  <div>
                    <div className="text-sm text-text-primary">{alert.message}</div>
                    <div className="text-xs text-text-secondary">
                      {new Date(alert.triggeredAt).toLocaleString()}
                    </div>
                  </div>
                  <button
                    onClick={() => acknowledgeAlert(alert.id)}
                    className="px-2 py-1 text-xs bg-bg-tertiary text-text-primary rounded hover:bg-bg-tertiary/80"
                  >
                    Acknowledge
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Exposure by Category */}
      <div data-testid="exposure-by-category" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Exposure by Category</h3>
        <div className="space-y-2">
          {exposureByCategory.map((cat) => (
            <div key={cat.category} className="flex items-center justify-between p-3 bg-bg-tertiary rounded-lg">
              <div className="flex items-center gap-3">
                <span className={clsx('px-2 py-1 rounded text-xs', riskLevelColors[cat.riskLevel])}>
                  {cat.riskLevel}
                </span>
                <div>
                  <div className="text-sm text-text-primary">{cat.category}</div>
                  <div className="text-xs text-text-secondary">{cat.positionCount} positions</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-text-primary">${cat.exposure.toFixed(2)}</div>
                <div className={cat.pnl >= 0 ? 'text-accent-green text-xs' : 'text-accent-red text-xs'}>
                  {cat.pnl >= 0 ? '+' : ''}${cat.pnl.toFixed(2)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Correlation Matrix */}
      <div data-testid="correlation-matrix" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Category Correlation</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left text-text-secondary">Categories</th>
                <th className="px-3 py-2 text-right text-text-secondary">Correlation</th>
              </tr>
            </thead>
            <tbody>
              {correlationData.map(([a, b, corr]) => (
                <tr key={`${a}-${b}`} className="border-t border-border">
                  <td className="px-3 py-2 text-text-primary">{a} ↔ {b}</td>
                  <td className={clsx(
                    'px-3 py-2 text-right',
                    corr > 0.3 ? 'text-accent-yellow' : 'text-accent-green'
                  )}>
                    {corr.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div data-testid="correlation-legend" className="flex items-center gap-4 mt-4 text-xs text-text-secondary">
          <span><span className="text-accent-green">●</span> Low positive correlation</span>
          <span><span className="text-accent-yellow">●</span> Moderate positive correlation</span>
          <span><span className="text-accent-red">●</span> High negative correlation</span>
        </div>
      </div>

      {/* Risk Heatmap */}
      <div data-testid="risk-heatmap" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Risk Heatmap</h3>
        <div className="grid grid-cols-3 gap-2">
          {exposureByCategory.map((cat) => (
            <div
              key={cat.category}
              className={clsx(
                'p-4 rounded-lg text-center',
                cat.riskLevel === 'low' && 'bg-accent-green/20',
                cat.riskLevel === 'medium' && 'bg-accent-yellow/20',
                cat.riskLevel === 'high' && 'bg-accent-red/20'
              )}
            >
              <div className="text-sm font-medium text-text-primary">{cat.category}</div>
              <div className="text-xs text-text-secondary">${cat.exposure.toFixed(0)}</div>
            </div>
          ))}
        </div>
        <div data-testid="heatmap-legend" className="flex items-center gap-4 mt-4 text-xs text-text-secondary">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-accent-green/20 rounded"></span> Low Risk
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-accent-yellow/20 rounded"></span> Medium Risk
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-accent-red/20 rounded"></span> High Risk
          </span>
        </div>
      </div>

      {/* Edit Limits Modal */}
      {showLimitModal && editingLimits && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={cancelLimitEdit}
        >
          <div
            className="bg-bg-secondary rounded-lg p-6 max-w-md w-full mx-4 border border-border"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-text-primary mb-4">Edit Risk Limits</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-text-secondary mb-1">Max Position Size ($)</label>
                <input
                  type="number"
                  value={editingLimits.maxPositionSize}
                  onChange={(e) => setEditingLimits({ ...editingLimits, maxPositionSize: parseFloat(e.target.value) || 0 })}
                  className="w-full bg-bg-tertiary border border-border rounded-lg px-3 py-2 text-text-primary"
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">Stop Loss (%)</label>
                <input
                  type="number"
                  value={editingLimits.stopLoss * 100}
                  onChange={(e) => setEditingLimits({ ...editingLimits, stopLoss: (parseFloat(e.target.value) || 0) / 100 })}
                  className="w-full bg-bg-tertiary border border-border rounded-lg px-3 py-2 text-text-primary"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-6">
              <button
                onClick={saveLimits}
                className="flex-1 py-2 bg-accent-blue text-white rounded-lg hover:bg-accent-blue/80"
              >
                Save
              </button>
              <button
                onClick={cancelLimitEdit}
                className="flex-1 py-2 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
