/**
 * Settings Page
 * Manage API key and export data snapshots.
 */
import { useMemo, useState } from 'react';
import { useActivity, useOrders, usePositions, useSystemConfig } from '../hooks/useDashboardData';

const STORAGE_KEY = 'dashboard_api_key';

function getStoredApiKey() {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.localStorage.getItem(STORAGE_KEY) ?? '';
}

function downloadFile(filename: string, contents: string, type: string) {
  const blob = new Blob([contents], { type });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(url);
}

function toCsv(rows: Array<Record<string, unknown>>) {
  if (rows.length === 0) {
    return '';
  }
  const headers = Object.keys(rows[0]);
  const escapeValue = (value: unknown) => {
    if (value === null || value === undefined) {
      return '';
    }
    const text = String(value);
    if (text.includes(',') || text.includes('\n') || text.includes('"')) {
      return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
  };
  const lines = rows.map((row) =>
    headers.map((key) => escapeValue(row[key])).join(',')
  );
  return [headers.join(','), ...lines].join('\n');
}

export function Settings() {
  const [apiKey, setApiKey] = useState(getStoredApiKey());
  const { data: activityData } = useActivity(500);
  const { data: positionsData } = usePositions();
  const { data: ordersData } = useOrders(500);
  const { data: systemConfig } = useSystemConfig();

  const activityRows = activityData ?? [];
  const positionsRows = positionsData ?? [];
  const ordersRows = ordersData ?? [];

  const apiKeyStatus = apiKey ? 'Stored' : 'Not set';

  const exports = useMemo(() => ([
    { label: 'Activity', rows: activityRows, filename: 'activity' },
    { label: 'Positions', rows: positionsRows, filename: 'positions' },
    { label: 'Orders', rows: ordersRows, filename: 'orders' },
  ]), [activityRows, positionsRows, ordersRows]);

  const handleSave = () => {
    if (typeof window === 'undefined') {
      return;
    }
    if (apiKey) {
      window.localStorage.setItem(STORAGE_KEY, apiKey);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    window.location.reload();
  };

  const handleClear = () => {
    setApiKey('');
  };

  return (
    <div className="px-6 py-6 space-y-6">
      <div>
        <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
          Settings
        </div>
        <h1 className="text-3xl font-semibold text-text-primary">Operator Preferences</h1>
        <p className="text-text-secondary">Manage API access and export live data snapshots.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm p-4 space-y-4">
          <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">API Key</div>
          <div className="text-sm text-text-secondary">
            Status: <span className="text-text-primary">{apiKeyStatus}</span>
          </div>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Paste dashboard API key"
            className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
          />
          <div className="flex items-center gap-3 text-xs">
            <button
              onClick={handleSave}
              className="rounded-full bg-accent-blue px-4 py-2 text-white"
            >
              Save & Reload
            </button>
            <button
              onClick={handleClear}
              className="rounded-full border border-border px-4 py-2 text-text-secondary"
            >
              Clear
            </button>
          </div>
          <div className="text-xs text-text-secondary">
            When API key auth is enabled, the dashboard uses this key for REST + SSE.
          </div>
        </div>

        <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm p-4 space-y-4">
          <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Environment</div>
          <div className="text-sm text-text-secondary">
            {systemConfig ? (
              <div className="space-y-1">
                <div>Env: <span className="text-text-primary">{systemConfig.environment}</span></div>
                <div>Version: <span className="text-text-primary">{systemConfig.version}</span></div>
                <div>Commit: <span className="text-text-primary">{systemConfig.commitHash}</span></div>
              </div>
            ) : (
              <div>System config unavailable.</div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm p-4 space-y-4">
        <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Exports</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {exports.map((item) => (
            <div key={item.label} className="bg-bg-tertiary rounded-xl p-4 space-y-3">
              <div className="text-sm text-text-primary">{item.label}</div>
              <div className="text-xs text-text-secondary">{item.rows.length} rows</div>
              <div className="flex items-center gap-2 text-xs">
                <button
                  onClick={() => downloadFile(`${item.filename}.json`, JSON.stringify(item.rows, null, 2), 'application/json')}
                  className="rounded-full border border-border px-3 py-1 text-text-secondary"
                >
                  JSON
                </button>
                <button
                  onClick={() => downloadFile(`${item.filename}.csv`, toCsv(item.rows as unknown as Array<Record<string, unknown>>), 'text/csv')}
                  className="rounded-full border border-border px-3 py-1 text-text-secondary"
                >
                  CSV
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
