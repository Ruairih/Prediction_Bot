/**
 * Settings Page
 * Manage themes, API key, and export data snapshots.
 */
import { useMemo, useState } from 'react';
import { useTheme, themes, type ThemeName } from '../contexts/ThemeContext';
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

// Theme preview colors for the selector
const themePreviewColors: Record<ThemeName, { bg: string; accent: string; text: string }> = {
  'midnight-pro': { bg: '#0a0c10', accent: '#58a6ff', text: '#e6edf3' },
  'aurora': { bg: '#0b0d14', accent: '#06b6d4', text: '#f3f4f6' },
  'cyber': { bg: '#0a0a0f', accent: '#00f0ff', text: '#ffffff' },
  'obsidian': { bg: '#000000', accent: '#d4a574', text: '#fafafa' },
  'daylight': { bg: '#f8f6f2', accent: '#0f6b6e', text: '#1a1a1a' },
};

function ThemeCard({
  themeName,
  isSelected,
  onClick
}: {
  themeName: ThemeName;
  isSelected: boolean;
  onClick: () => void;
}) {
  const theme = themes[themeName];
  const preview = themePreviewColors[themeName];

  return (
    <button
      onClick={onClick}
      className={`
        relative group text-left rounded-xl p-4 transition-all duration-300
        ${isSelected
          ? 'ring-2 ring-offset-2 ring-offset-bg-primary ring-accent-primary scale-[1.02]'
          : 'hover:scale-[1.01]'
        }
      `}
      style={{
        background: preview.bg,
        border: `1px solid ${isSelected ? preview.accent : 'rgba(255,255,255,0.1)'}`,
      }}
    >
      {/* Selection indicator */}
      {isSelected && (
        <div
          className="absolute top-3 right-3 w-5 h-5 rounded-full flex items-center justify-center text-xs"
          style={{ background: preview.accent, color: theme.isDark ? '#fff' : '#000' }}
        >
          ✓
        </div>
      )}

      {/* Preview bar */}
      <div className="flex gap-1.5 mb-3">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: preview.accent }}
        />
        <div
          className="w-3 h-3 rounded-full opacity-60"
          style={{ background: preview.accent }}
        />
        <div
          className="w-3 h-3 rounded-full opacity-30"
          style={{ background: preview.accent }}
        />
      </div>

      {/* Theme name */}
      <div
        className="font-semibold text-sm mb-1"
        style={{ color: preview.text }}
      >
        {theme.label}
      </div>

      {/* Description */}
      <div
        className="text-xs opacity-70"
        style={{ color: preview.text }}
      >
        {theme.description}
      </div>

      {/* Decorative gradient overlay */}
      <div
        className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
        style={{
          background: `radial-gradient(circle at 50% 0%, ${preview.accent}15, transparent 70%)`,
        }}
      />
    </button>
  );
}

export function Settings() {
  const { themeName, setTheme } = useTheme();
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
    { label: 'Activity', rows: activityRows, filename: 'activity', icon: '≋' },
    { label: 'Positions', rows: positionsRows, filename: 'positions', icon: '◈' },
    { label: 'Orders', rows: ordersRows, filename: 'orders', icon: '▣' },
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
    <div className="px-6 py-6 space-y-8 max-w-6xl">
      {/* Header */}
      <div className="animate-fade-in">
        <div className="text-label uppercase tracking-[0.3em] text-text-muted">
          Settings
        </div>
        <h1 className="text-3xl font-semibold text-text-primary mt-1">
          Operator Preferences
        </h1>
        <p className="text-text-secondary mt-2">
          Customize your trading experience with themes, API access, and data exports.
        </p>
      </div>

      {/* Theme Selector */}
      <div className="card p-6 space-y-5 animate-fade-in" style={{ animationDelay: '50ms' }}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-label uppercase tracking-[0.3em] text-text-muted">
              Appearance
            </div>
            <h2 className="text-lg font-semibold text-text-primary mt-1">
              Choose Your Theme
            </h2>
          </div>
          <div className="text-xs text-text-muted px-3 py-1.5 rounded-full bg-bg-tertiary">
            {themes[themeName].label} active
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {(Object.keys(themes) as ThemeName[]).map((name) => (
            <ThemeCard
              key={name}
              themeName={name}
              isSelected={themeName === name}
              onClick={() => setTheme(name)}
            />
          ))}
        </div>

        <div className="text-xs text-text-muted pt-2 border-t border-border-subtle">
          Theme changes are applied instantly and saved to your browser.
        </div>
      </div>

      {/* API Key & Environment */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-5 space-y-4 animate-fade-in" style={{ animationDelay: '100ms' }}>
          <div>
            <div className="text-label uppercase tracking-[0.3em] text-text-muted">
              Authentication
            </div>
            <h3 className="text-base font-semibold text-text-primary mt-1">
              API Key
            </h3>
          </div>

          <div className="flex items-center gap-2 text-sm">
            <div
              className={`w-2 h-2 rounded-full ${apiKey ? 'bg-positive' : 'bg-text-muted'}`}
              aria-hidden="true"
            />
            <span className="text-text-secondary">Status:</span>
            <span className="text-text-primary font-medium">{apiKeyStatus}</span>
          </div>

          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Paste dashboard API key"
            className="w-full rounded-lg border border-border bg-bg-tertiary px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-all"
          />

          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              className="btn btn-primary text-sm"
            >
              Save & Reload
            </button>
            <button
              onClick={handleClear}
              className="btn btn-secondary text-sm"
            >
              Clear
            </button>
          </div>

          <div className="text-xs text-text-muted">
            Required when API key auth is enabled on the monitoring dashboard.
          </div>
        </div>

        <div className="card p-5 space-y-4 animate-fade-in" style={{ animationDelay: '150ms' }}>
          <div>
            <div className="text-label uppercase tracking-[0.3em] text-text-muted">
              System
            </div>
            <h3 className="text-base font-semibold text-text-primary mt-1">
              Environment
            </h3>
          </div>

          {systemConfig ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2 border-b border-border-subtle">
                <span className="text-sm text-text-secondary">Environment</span>
                <span className="text-sm text-text-primary font-mono bg-bg-tertiary px-2 py-0.5 rounded">
                  {systemConfig.environment}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border-subtle">
                <span className="text-sm text-text-secondary">Version</span>
                <span className="text-sm text-text-primary font-mono bg-bg-tertiary px-2 py-0.5 rounded">
                  {systemConfig.version}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-text-secondary">Commit</span>
                <span className="text-sm text-text-primary font-mono bg-bg-tertiary px-2 py-0.5 rounded">
                  {systemConfig.commitHash.slice(0, 7)}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-sm text-text-muted py-4 text-center">
              System config unavailable
            </div>
          )}
        </div>
      </div>

      {/* Exports */}
      <div className="card p-5 space-y-5 animate-fade-in" style={{ animationDelay: '200ms' }}>
        <div>
          <div className="text-label uppercase tracking-[0.3em] text-text-muted">
            Data
          </div>
          <h3 className="text-base font-semibold text-text-primary mt-1">
            Export Snapshots
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {exports.map((item) => (
            <div
              key={item.label}
              className="group bg-bg-tertiary rounded-xl p-5 border border-border-subtle hover:border-border transition-all"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg bg-bg-secondary flex items-center justify-center text-lg text-accent-primary">
                  {item.icon}
                </div>
                <div>
                  <div className="text-sm font-medium text-text-primary">{item.label}</div>
                  <div className="text-xs text-text-muted tabular-nums">{item.rows.length} rows</div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => downloadFile(`${item.filename}.json`, JSON.stringify(item.rows, null, 2), 'application/json')}
                  className="flex-1 btn btn-secondary text-xs py-2"
                >
                  Export JSON
                </button>
                <button
                  onClick={() => downloadFile(`${item.filename}.csv`, toCsv(item.rows as unknown as Array<Record<string, unknown>>), 'text/csv')}
                  className="flex-1 btn btn-secondary text-xs py-2"
                >
                  Export CSV
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-text-muted py-4 animate-fade-in" style={{ animationDelay: '250ms' }}>
        Polymarket Trading Dashboard · Built with precision
      </div>
    </div>
  );
}
