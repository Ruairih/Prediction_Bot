/**
 * P&L Breakdown Tabs Component
 */
import { useState } from 'react';
import clsx from 'clsx';
import { PnlBadge } from '../common/PnlBadge';
import type { PnlBucket } from '../../types';

type Interval = 'daily' | 'weekly' | 'monthly';

export interface PnlBreakdownProps {
  daily: PnlBucket[];
  weekly: PnlBucket[];
  monthly: PnlBucket[];
}

export function PnlBreakdown({ daily, weekly, monthly }: PnlBreakdownProps) {
  const [activeTab, setActiveTab] = useState<Interval>('daily');

  const data = {
    daily,
    weekly,
    monthly,
  }[activeTab];

  return (
    <div
      data-testid="pnl-breakdown"
      className="bg-bg-secondary rounded-lg border border-border overflow-hidden"
    >
      <div className="flex border-b border-border" role="tablist">
        {(['daily', 'weekly', 'monthly'] as Interval[]).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              'flex-1 px-4 py-3 text-sm font-medium transition-colors',
              activeTab === tab
                ? 'bg-bg-tertiary text-text-primary border-b-2 border-accent-blue'
                : 'text-text-secondary hover:text-text-primary'
            )}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="p-4">
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {data.map((bucket) => (
            <div
              key={bucket.period}
              className="flex items-center justify-between py-2 border-b border-border last:border-0"
            >
              <div>
                <div className="text-sm text-text-primary">{bucket.period}</div>
                <div className="text-xs text-text-secondary">
                  {bucket.trades} trades ({bucket.wins}W / {bucket.losses}L)
                </div>
              </div>
              <PnlBadge value={bucket.pnl} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
