/**
 * Risk Page
 * Real-time exposure and guardrail overview.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { useBotStatus, useRisk } from '../hooks/useDashboardData';
import { updateRiskLimits, pauseTrading, resumeTrading, cancelAllOrders, flattenPositions } from '../api/dashboard';
import { useToast } from '../contexts/ToastContext';
import { ConfirmDialog, type ConfirmDialogVariant } from '../components/common/ConfirmDialog';
import type { RiskLimits } from '../types';

/** Configuration for a dangerous action confirmation dialog */
interface DangerousActionConfig {
  title: string;
  description: string;
  consequences: string[];
  confirmText: string;
  variant: ConfirmDialogVariant;
  /** If true, requires typed confirmation in live mode */
  requiresDoubleConfirmInLive: boolean;
  confirmationPhrase?: string;
  action: () => Promise<void>;
}

// Validation error type
interface ValidationErrors {
  maxPositionSize?: string;
  maxTotalExposure?: string;
  maxPositions?: string;
  minBalanceReserve?: string;
  priceThreshold?: string;
  stopLoss?: string;
  profitTarget?: string;
  minHoldDays?: string;
}

// Validation rules for risk limits
function validateRiskLimits(limits: RiskLimits): ValidationErrors {
  const errors: ValidationErrors = {};

  // Max Position Size: must be positive number
  if (limits.maxPositionSize <= 0) {
    errors.maxPositionSize = 'Position size must be greater than 0';
  } else if (!Number.isFinite(limits.maxPositionSize)) {
    errors.maxPositionSize = 'Please enter a valid number';
  }

  // Max Total Exposure: must be non-negative
  if (limits.maxTotalExposure < 0) {
    errors.maxTotalExposure = 'Total exposure cannot be negative';
  } else if (!Number.isFinite(limits.maxTotalExposure)) {
    errors.maxTotalExposure = 'Please enter a valid number';
  }

  // Max Positions: must be positive integer
  if (limits.maxPositions <= 0) {
    errors.maxPositions = 'Must have at least 1 position allowed';
  } else if (!Number.isInteger(limits.maxPositions)) {
    errors.maxPositions = 'Must be a whole number';
  } else if (!Number.isFinite(limits.maxPositions)) {
    errors.maxPositions = 'Please enter a valid number';
  }

  // Min Balance Reserve: must be non-negative
  if (limits.minBalanceReserve < 0) {
    errors.minBalanceReserve = 'Balance reserve cannot be negative';
  } else if (!Number.isFinite(limits.minBalanceReserve)) {
    errors.minBalanceReserve = 'Please enter a valid number';
  }

  // Price Threshold: must be between 0 and 1 (0-100%)
  if (limits.priceThreshold < 0 || limits.priceThreshold > 1) {
    errors.priceThreshold = 'Must be between 0 and 1 (0-100%)';
  } else if (!Number.isFinite(limits.priceThreshold)) {
    errors.priceThreshold = 'Please enter a valid number';
  }

  // Stop Loss: must be between 0 and 1, and less than price threshold
  if (limits.stopLoss < 0 || limits.stopLoss > 1) {
    errors.stopLoss = 'Must be between 0 and 1 (0-100%)';
  } else if (limits.stopLoss >= limits.priceThreshold) {
    errors.stopLoss = 'Stop loss must be below entry price threshold';
  } else if (!Number.isFinite(limits.stopLoss)) {
    errors.stopLoss = 'Please enter a valid number';
  }

  // Profit Target: must be between 0 and 1, and above price threshold
  if (limits.profitTarget < 0 || limits.profitTarget > 1) {
    errors.profitTarget = 'Must be between 0 and 1 (0-100%)';
  } else if (limits.profitTarget <= limits.priceThreshold) {
    errors.profitTarget = 'Profit target must be above entry price threshold';
  } else if (!Number.isFinite(limits.profitTarget)) {
    errors.profitTarget = 'Please enter a valid number';
  }

  // Min Hold Days: must be non-negative integer
  if (limits.minHoldDays < 0) {
    errors.minHoldDays = 'Hold days cannot be negative';
  } else if (!Number.isInteger(limits.minHoldDays)) {
    errors.minHoldDays = 'Must be a whole number';
  } else if (!Number.isFinite(limits.minHoldDays)) {
    errors.minHoldDays = 'Please enter a valid number';
  }

  return errors;
}

export function Risk() {
  const { data: riskData, isLoading, refetch } = useRisk();
  const { data: statusData } = useBotStatus();
  const [editLimits, setEditLimits] = useState(riskData?.limits);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});
  const [touched, setTouched] = useState<Set<keyof RiskLimits>>(new Set());
  const [confirmDialog, setConfirmDialog] = useState<DangerousActionConfig | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const toast = useToast();

  // Determine if we're in live mode (requires extra confirmation for dangerous actions)
  const isLiveMode = statusData?.mode === 'live';

  useEffect(() => {
    if (riskData?.limits) {
      setEditLimits(riskData.limits);
      setValidationErrors({});
      setTouched(new Set());
    }
  }, [riskData]);

  // Validate on edit limits change
  useEffect(() => {
    if (editLimits) {
      const errors = validateRiskLimits(editLimits);
      setValidationErrors(errors);
    }
  }, [editLimits]);

  // Check if form has any validation errors
  const hasErrors = useMemo(() => {
    return Object.keys(validationErrors).length > 0;
  }, [validationErrors]);

  const currentExposure = riskData?.currentExposure ?? 0;
  const exposurePercent = riskData?.exposurePercent ?? 0;
  const leverage = exposurePercent > 0 ? exposurePercent / 100 : 0;
  // Calculate total deployable capital from exposure and exposure percent
  const totalAssets = exposurePercent > 0 ? (currentExposure / exposurePercent) * 100 : 0;

  const alerts = useMemo(() => {
    const result: { message: string; severity: 'warning' | 'critical' }[] = [];
    if (exposurePercent > 80) {
      result.push({ message: 'Exposure above 80% of deployable capital.', severity: 'critical' });
    } else if (exposurePercent > 60) {
      result.push({ message: 'Exposure above 60% of deployable capital.', severity: 'warning' });
    }
    return result;
  }, [exposurePercent]);

  const handleLimitChange = useCallback((key: keyof RiskLimits, value: number) => {
    if (!editLimits) return;
    setEditLimits({ ...editLimits, [key]: value });
    setTouched((prev) => new Set(prev).add(key));
  }, [editLimits]);

  const handleBlur = useCallback((key: keyof RiskLimits) => {
    setTouched((prev) => new Set(prev).add(key));
  }, []);

  const handleSaveLimits = async () => {
    if (!editLimits || hasErrors) return;
    try {
      await updateRiskLimits(editLimits);
      await refetch();
      toast.success('Risk limits saved', 'Your risk limit changes have been applied successfully.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      toast.error('Failed to save limits', message);
    }
  };

  // Helper to get error message for a field (only show if touched)
  const getFieldError = (key: keyof RiskLimits): string | undefined => {
    if (touched.has(key)) {
      return validationErrors[key as keyof ValidationErrors];
    }
    return undefined;
  };

  // Helper to generate unique error ID for aria-describedby
  const getErrorId = (key: keyof RiskLimits): string => `${key}-error`;

  // Handlers for dangerous actions that require confirmation
  const handlePauseTrading = useCallback(() => {
    if (statusData?.mode === 'paused') {
      // Resume trading doesn't need confirmation
      resumeTrading()
        .then(() => toast.success('Trading Resumed', 'The bot will now process new signals.'))
        .catch((err) => toast.error('Resume Failed', err instanceof Error ? err.message : 'Unknown error'));
      return;
    }

    setConfirmDialog({
      title: 'Pause Trading',
      description: 'This will immediately stop the bot from processing new signals and placing orders.',
      consequences: [
        'No new orders will be placed',
        'Existing orders will remain active',
        'Open positions will not be closed automatically',
      ],
      confirmText: 'Pause Trading',
      variant: 'warning',
      requiresDoubleConfirmInLive: true,
      confirmationPhrase: 'PAUSE',
      action: async () => {
        await pauseTrading('risk_panel');
        toast.success('Trading Paused', 'The bot has stopped processing new signals.');
      },
    });
  }, [statusData?.mode, toast]);

  const handleCancelAllOrders = useCallback(() => {
    setConfirmDialog({
      title: 'Cancel All Orders',
      description: 'This will immediately cancel all pending and live orders across all markets.',
      consequences: [
        'All pending orders will be cancelled',
        'Reserved capital will be released',
        'You may miss fill opportunities',
      ],
      confirmText: 'Cancel All Orders',
      variant: 'warning',
      requiresDoubleConfirmInLive: true,
      confirmationPhrase: 'CANCEL',
      action: async () => {
        await cancelAllOrders();
        toast.success('Orders Cancelled', 'All orders have been cancelled successfully.');
      },
    });
  }, [toast]);

  const handleFlattenPositions = useCallback(() => {
    setConfirmDialog({
      title: 'Flatten All Positions',
      description: 'This will immediately close all open positions at current market prices. This action may result in significant losses if markets are illiquid.',
      consequences: [
        'All positions will be sold immediately',
        'Realized P&L will be locked in',
        'Slippage may occur in illiquid markets',
        `Current exposure: $${currentExposure.toFixed(2)}`,
      ],
      confirmText: 'Flatten All',
      variant: 'danger',
      requiresDoubleConfirmInLive: true,
      confirmationPhrase: 'FLATTEN',
      action: async () => {
        await flattenPositions('risk_panel');
        toast.success('Positions Flattened', 'All positions have been closed.');
      },
    });
  }, [currentExposure, toast]);

  const handleConfirmAction = useCallback(async () => {
    if (!confirmDialog) return;
    setIsActionLoading(true);
    try {
      await confirmDialog.action();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      toast.error('Action Failed', message);
    } finally {
      setIsActionLoading(false);
      setConfirmDialog(null);
    }
  }, [confirmDialog, toast]);

  const handleCloseDialog = useCallback(() => {
    if (!isActionLoading) {
      setConfirmDialog(null);
    }
  }, [isActionLoading]);

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
                <div className="space-y-1">
                  <label htmlFor="maxPositionSize" className="text-text-secondary block">
                    Max Position Size ($)
                  </label>
                  <input
                    id="maxPositionSize"
                    type="number"
                    min="0"
                    step="1"
                    value={editLimits.maxPositionSize}
                    onChange={(e) => handleLimitChange('maxPositionSize', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('maxPositionSize')}
                    aria-invalid={!!getFieldError('maxPositionSize')}
                    aria-describedby={getFieldError('maxPositionSize') ? getErrorId('maxPositionSize') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('maxPositionSize') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('maxPositionSize') && (
                    <p id={getErrorId('maxPositionSize')} className="text-negative text-xs mt-1">
                      {getFieldError('maxPositionSize')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="maxTotalExposure" className="text-text-secondary block">
                    Max Total Exposure ($)
                  </label>
                  <input
                    id="maxTotalExposure"
                    type="number"
                    min="0"
                    step="1"
                    value={editLimits.maxTotalExposure}
                    onChange={(e) => handleLimitChange('maxTotalExposure', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('maxTotalExposure')}
                    aria-invalid={!!getFieldError('maxTotalExposure')}
                    aria-describedby={getFieldError('maxTotalExposure') ? getErrorId('maxTotalExposure') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('maxTotalExposure') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('maxTotalExposure') && (
                    <p id={getErrorId('maxTotalExposure')} className="text-negative text-xs mt-1">
                      {getFieldError('maxTotalExposure')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="maxPositions" className="text-text-secondary block">
                    Max Positions
                  </label>
                  <input
                    id="maxPositions"
                    type="number"
                    min="1"
                    step="1"
                    value={editLimits.maxPositions}
                    onChange={(e) => handleLimitChange('maxPositions', parseInt(e.target.value, 10) || 0)}
                    onBlur={() => handleBlur('maxPositions')}
                    aria-invalid={!!getFieldError('maxPositions')}
                    aria-describedby={getFieldError('maxPositions') ? getErrorId('maxPositions') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('maxPositions') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('maxPositions') && (
                    <p id={getErrorId('maxPositions')} className="text-negative text-xs mt-1">
                      {getFieldError('maxPositions')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="minBalanceReserve" className="text-text-secondary block">
                    Min Balance Reserve ($)
                  </label>
                  <input
                    id="minBalanceReserve"
                    type="number"
                    min="0"
                    step="1"
                    value={editLimits.minBalanceReserve}
                    onChange={(e) => handleLimitChange('minBalanceReserve', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('minBalanceReserve')}
                    aria-invalid={!!getFieldError('minBalanceReserve')}
                    aria-describedby={getFieldError('minBalanceReserve') ? getErrorId('minBalanceReserve') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('minBalanceReserve') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('minBalanceReserve') && (
                    <p id={getErrorId('minBalanceReserve')} className="text-negative text-xs mt-1">
                      {getFieldError('minBalanceReserve')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="priceThreshold" className="text-text-secondary block">
                    Price Threshold (0-1)
                  </label>
                  <input
                    id="priceThreshold"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={editLimits.priceThreshold}
                    onChange={(e) => handleLimitChange('priceThreshold', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('priceThreshold')}
                    aria-invalid={!!getFieldError('priceThreshold')}
                    aria-describedby={getFieldError('priceThreshold') ? getErrorId('priceThreshold') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('priceThreshold') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('priceThreshold') && (
                    <p id={getErrorId('priceThreshold')} className="text-negative text-xs mt-1">
                      {getFieldError('priceThreshold')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="stopLoss" className="text-text-secondary block">
                    Stop Loss (0-1)
                  </label>
                  <input
                    id="stopLoss"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={editLimits.stopLoss}
                    onChange={(e) => handleLimitChange('stopLoss', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('stopLoss')}
                    aria-invalid={!!getFieldError('stopLoss')}
                    aria-describedby={getFieldError('stopLoss') ? getErrorId('stopLoss') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('stopLoss') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('stopLoss') && (
                    <p id={getErrorId('stopLoss')} className="text-negative text-xs mt-1">
                      {getFieldError('stopLoss')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="profitTarget" className="text-text-secondary block">
                    Profit Target (0-1)
                  </label>
                  <input
                    id="profitTarget"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={editLimits.profitTarget}
                    onChange={(e) => handleLimitChange('profitTarget', parseFloat(e.target.value) || 0)}
                    onBlur={() => handleBlur('profitTarget')}
                    aria-invalid={!!getFieldError('profitTarget')}
                    aria-describedby={getFieldError('profitTarget') ? getErrorId('profitTarget') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('profitTarget') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('profitTarget') && (
                    <p id={getErrorId('profitTarget')} className="text-negative text-xs mt-1">
                      {getFieldError('profitTarget')}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <label htmlFor="minHoldDays" className="text-text-secondary block">
                    Min Hold Days
                  </label>
                  <input
                    id="minHoldDays"
                    type="number"
                    min="0"
                    step="1"
                    value={editLimits.minHoldDays}
                    onChange={(e) => handleLimitChange('minHoldDays', parseInt(e.target.value, 10) || 0)}
                    onBlur={() => handleBlur('minHoldDays')}
                    aria-invalid={!!getFieldError('minHoldDays')}
                    aria-describedby={getFieldError('minHoldDays') ? getErrorId('minHoldDays') : undefined}
                    className={clsx(
                      'w-full rounded-lg border bg-bg-tertiary px-3 py-2 text-text-primary',
                      getFieldError('minHoldDays') ? 'border-negative' : 'border-border'
                    )}
                  />
                  {getFieldError('minHoldDays') && (
                    <p id={getErrorId('minHoldDays')} className="text-negative text-xs mt-1">
                      {getFieldError('minHoldDays')}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex gap-2 mt-4 items-center">
                <button
                  onClick={handleSaveLimits}
                  disabled={hasErrors}
                  aria-disabled={hasErrors}
                  className={clsx(
                    'px-4 py-2 rounded-full text-xs font-semibold transition-colors',
                    hasErrors
                      ? 'bg-bg-tertiary text-text-muted cursor-not-allowed'
                      : 'bg-accent-blue text-white hover:bg-accent-blue/80'
                  )}
                >
                  Save Limits
                </button>
                <button
                  onClick={() => {
                    setEditLimits(riskData?.limits);
                    setTouched(new Set());
                  }}
                  className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary"
                >
                  Reset
                </button>
                {hasErrors && (
                  <span className="text-negative text-xs ml-2">
                    Please fix validation errors before saving
                  </span>
                )}
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
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-text-primary">Manual Overrides</h3>
          {isLiveMode && (
            <span className="px-2 py-1 rounded-full bg-negative/20 text-negative text-xs font-semibold">
              LIVE MODE
            </span>
          )}
        </div>
        <div className="text-sm text-text-secondary mb-4">
          Manual overrides apply immediately and are recorded in the audit log.
          {isLiveMode && ' Dangerous actions require typed confirmation in live mode.'}
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handlePauseTrading}
            aria-label={statusData?.mode === 'paused' ? 'Resume Trading' : 'Pause Trading'}
            className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            {statusData?.mode === 'paused' ? 'Resume Trading' : 'Pause Trading'}
          </button>
          <button
            onClick={handleCancelAllOrders}
            aria-label="Cancel All Orders"
            className="px-4 py-2 rounded-full border border-border text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            Cancel All Orders
          </button>
          <button
            onClick={handleFlattenPositions}
            aria-label="Flatten All Positions"
            className="px-4 py-2 rounded-full border border-negative/50 text-xs font-semibold text-negative hover:bg-negative/10 transition-colors"
          >
            Flatten Positions
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {confirmDialog && (
        <ConfirmDialog
          isOpen={true}
          onClose={handleCloseDialog}
          onConfirm={handleConfirmAction}
          title={confirmDialog.title}
          description={confirmDialog.description}
          consequences={confirmDialog.consequences}
          confirmText={confirmDialog.confirmText}
          variant={confirmDialog.variant}
          requiresTypedConfirmation={isLiveMode && confirmDialog.requiresDoubleConfirmInLive}
          confirmationPhrase={confirmDialog.confirmationPhrase}
          isLoading={isActionLoading}
        />
      )}
    </div>
  );
}
