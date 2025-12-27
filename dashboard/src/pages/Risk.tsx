/**
 * Risk Page
 * Real-time exposure and guardrail overview.
 */
import { useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { useBotStatus, useRisk } from '../hooks/useDashboardData';
import { updateRiskLimits, pauseTrading, resumeTrading, cancelAllOrders, flattenPositions } from '../api/dashboard';
import type { RiskLimits } from '../types';

export function Risk() {
  const { data: riskData, isLoading, refetch } = useRisk();
  const { data: statusData } = useBotStatus();
  const [editLimits, setEditLimits] = useState(riskData?.limits);

  useEffect(() => {
    if (riskData?.limits) {
      setEditLimits(riskData.limits);
    }
  }, [riskData]);

  const currentExposure = riskData?.currentExposure ?? 0;
  const exposurePercent = riskData?.exposurePercent ?? 0;
  const leverage = exposurePercent > 0 ? exposurePercent / 100 : 0;

  const alerts = useMemo(() => {
    const result: { message: string; severity: 'warning' | 'critical' }[] = [];
    if (exposurePercent > 80) {
      result.push({ message: 'Exposure above 80% of deployable capital.', severity: 'critical' });
    } else if (exposurePercent > 60) {
      result.push({ message: 'Exposure above 60% of deployable capital.', severity: 'warning' });
    }
    return result;
  }, [exposurePercent]);

  const handleLimitChange = (key: keyof RiskLimits, value: number) => {
    if (!editLimits) return;
    setEditLimits({ ...editLimits, [key]: value });
  };

  const handleSaveLimits = async () => {
    if (!editLimits) return;
    await updateRiskLimits(editLimits);
    await refetch();
  };

  return (
    <div className="px-6 py-6 space-y-6">
      <div>
        <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
          Risk
        </div>
        <h1 className="text-3xl font-semibold text-text-primary">Exposure & Guardrails</h1>
        <p className="text-text-secondary">
          Track real-time exposure and apply manual limits from a single panel.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <div className="text-text-secondary text-sm mb-1">Current Exposure</div>
          <div className="text-2xl font-semibold text-text-primary">
            ${currentExposure.toFixed(2)}
          </div>
        </div>
        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <div className="text-text-secondary text-sm mb-1">Deployable Capital</div>
          <div className="text-2xl font-semibold text-text-primary">
            ${totalAssets.toFixed(2)}
          </div>
        </div>
        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <div className="text-text-secondary text-sm mb-1">Exposure %</div>
          <div className="text-2xl font-semibold text-text-primary">
            {exposurePercent.toFixed(1)}%
          </div>
        </div>
        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <div className="text-text-secondary text-sm mb-1">Leverage</div>
          <div className="text-2xl font-semibold text-text-primary">
            {leverage.toFixed(2)}x
          </div>
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <h3 className="text-lg font-semibold text-text-primary mb-3">Exposure Meter</h3>
        <div className="relative h-3 bg-bg-tertiary rounded-full overflow-hidden">
          <div
            role="progressbar"
            aria-valuenow={exposurePercent}
            aria-valuemin={0}
            aria-valuemax={100}
            className={clsx(
              'absolute h-full rounded-full transition-all',
              exposurePercent < 60 && 'bg-accent-green',
              exposurePercent >= 60 && exposurePercent < 80 && 'bg-accent-yellow',
              exposurePercent >= 80 && 'bg-accent-red'
            )}
            style={{ width: `${Math.min(exposurePercent, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-text-secondary mt-2">
          <span>0%</span>
          <span>{exposurePercent.toFixed(1)}%</span>
          <span>100%</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Risk Limits</h3>
            <span className="text-xs text-text-secondary">
              {isLoading ? 'Syncing...' : 'Editable'}
            </span>
          </div>
          {!editLimits ? (
            <div className="text-sm text-text-secondary">No limits available yet.</div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <label className="space-y-1">
                  <span className="text-text-secondary">Max Position Size</span>
                  <input
                    type="number"
                    value={editLimits.maxPositionSize}
                    onChange={(e) => handleLimitChange('maxPositionSize', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Max Total Exposure</span>
                  <input
                    type="number"
                    value={editLimits.maxTotalExposure}
                    onChange={(e) => handleLimitChange('maxTotalExposure', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Max Positions</span>
                  <input
                    type="number"
                    value={editLimits.maxPositions}
                    onChange={(e) => handleLimitChange('maxPositions', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Min Balance Reserve</span>
                  <input
                    type="number"
                    value={editLimits.minBalanceReserve}
                    onChange={(e) => handleLimitChange('minBalanceReserve', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Price Threshold</span>
                  <input
                    type="number"
                    step="0.01"
                    value={editLimits.priceThreshold}
                    onChange={(e) => handleLimitChange('priceThreshold', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Stop Loss</span>
                  <input
                    type="number"
                    step="0.01"
                    value={editLimits.stopLoss}
                    onChange={(e) => handleLimitChange('stopLoss', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Profit Target</span>
                  <input
                    type="number"
                    step="0.01"
                    value={editLimits.profitTarget}
                    onChange={(e) => handleLimitChange('profitTarget', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-text-secondary">Min Hold Days</span>
                  <input
                    type="number"
                    value={editLimits.minHoldDays}
                    onChange={(e) => handleLimitChange('minHoldDays', parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-text-primary"
                  />
                </label>
              </div>
              <div className="flex gap-2 mt-4">
                <button
                  onClick={handleSaveLimits}
                  className="px-4 py-2 rounded-full bg-accent-blue text-white text-xs font-semibold hover:bg-accent-blue/80"
                >
                  Save Limits
                </button>
                <button
                  onClick={() => setEditLimits(riskData?.limits)}
                  className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary"
                >
                  Reset
                </button>
              </div>
            </>
          )}
        </div>

        <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Active Alerts</h3>
          {alerts.length === 0 ? (
            <div className="text-text-secondary text-sm">No risk alerts triggered.</div>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.message}
                  className={clsx(
                    'border rounded-xl p-3 text-sm',
                    alert.severity === 'critical'
                      ? 'border-accent-red/40 bg-accent-red/10 text-accent-red'
                      : 'border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow'
                  )}
                >
                  {alert.message}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm">
        <h3 className="text-lg font-semibold text-text-primary mb-3">Manual Overrides</h3>
        <div className="text-sm text-text-secondary mb-4">
          Manual overrides apply immediately and are recorded in the audit log.
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={async () => {
              if (statusData?.mode === 'paused') {
                await resumeTrading();
              } else {
                await pauseTrading('risk_panel');
              }
            }}
            className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary"
          >
            {statusData?.mode === 'paused' ? 'Resume Trading' : 'Pause Trading'}
          </button>
          <button
            onClick={async () => {
              await cancelAllOrders();
            }}
            className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary"
          >
            Cancel All Orders
          </button>
          <button
            onClick={async () => {
              await flattenPositions('risk_panel');
            }}
            className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary"
          >
            Flatten Positions
          </button>
        </div>
      </div>
    </div>
  );
}
