/**
 * System Page
 * System health and configuration
 */
import { useState, useRef, useEffect } from 'react';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { useHealth, useSystemConfig, useLogs } from '../hooks/useDashboardData';
import type { SystemHealth, LogEntry, LogLevel, SystemConfig } from '../types';

const statusColors = {
  healthy: 'bg-accent-green',
  degraded: 'bg-accent-yellow',
  unhealthy: 'bg-accent-red',
  unknown: 'bg-text-secondary',
};

const logLevelColors = {
  debug: 'text-text-secondary',
  info: 'text-accent-blue',
  warning: 'text-accent-yellow',
  error: 'text-accent-red',
};

export function System() {
  const { data: healthData, isLoading: healthLoading, error: healthError } = useHealth();
  const { data: configData } = useSystemConfig();
  const { data: logsData } = useLogs(200);
  const health: SystemHealth = healthData ?? {
    overall: 'unknown',
    services: [],
    websocket: { connected: false, lastMessageAt: null, reconnectAttempts: 0, subscriptions: 0 },
    database: { connected: false, latencyMs: 0, poolSize: 0, activeConnections: 0 },
    rateLimits: [],
    uptime: 0,
    lastHealthCheck: new Date().toISOString(),
  };
  const logs: LogEntry[] = logsData ?? [];
  const config: SystemConfig = configData ?? {
    environment: 'development',
    version: '0.0.0',
    commitHash: 'unknown',
    apiBaseUrl: 'http://localhost:9050',
    wsBaseUrl: 'ws://localhost:9050',
    features: {},
  };
  const [logLevel, setLogLevel] = useState<LogLevel | 'all'>('all');
  const [logSearch, setLogSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const filteredLogs = logs.filter((log) => {
    if (logLevel !== 'all' && log.level !== logLevel) return false;
    if (logSearch && !log.message.toLowerCase().includes(logSearch.toLowerCase())) return false;
    return true;
  });

  // Auto-scroll to bottom when enabled and logs change
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll]);

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${mins}m`;
  };

  const [copySuccess, setCopySuccess] = useState<boolean | null>(null);

  const copyConfig = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
        setCopySuccess(true);
      } else {
        // Fallback for non-secure contexts
        const textArea = document.createElement('textarea');
        textArea.value = JSON.stringify(config, null, 2);
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopySuccess(true);
      }
      setTimeout(() => setCopySuccess(null), 2000);
    } catch {
      setCopySuccess(false);
      setTimeout(() => setCopySuccess(null), 2000);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">System</h1>
          <p className="text-text-secondary">Monitor system health and configuration</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
        >
          Refresh
        </button>
      </div>

      {healthLoading && (
        <div className="text-sm text-text-secondary">Refreshing health checks...</div>
      )}

      {healthError && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">Unable to load system health.</p>
        </div>
      )}

      {/* Overall Health & Uptime */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div data-testid="overall-health-status" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-2">Overall Health</div>
          <div className="flex items-center gap-2">
            <div data-status={health.overall} className={clsx('w-3 h-3 rounded-full', statusColors[health.overall])} />
            <span className="text-xl font-bold text-text-primary capitalize">{health.overall}</span>
          </div>
        </div>

        <div data-testid="system-uptime" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-2">Uptime</div>
          <div className="text-xl font-bold text-text-primary">
            {formatUptime(config.uptime ?? health.uptime ?? 0)}
          </div>
        </div>

        <div className="bg-bg-secondary rounded-lg p-4 border border-border">
          <div className="text-text-secondary text-sm mb-2">Last Updated</div>
          <div className="text-xl font-bold text-text-primary">
            {formatDistanceToNow(new Date(health.lastHealthCheck), { addSuffix: true })}
          </div>
        </div>
      </div>

      {/* Service Status Grid */}
      <div data-testid="system-health" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Services</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {health.services.map((service) => (
            <div
              key={service.name}
              data-testid="service-status-card"
              className="bg-bg-tertiary rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-text-primary">{service.name}</span>
                <div className={clsx('w-2 h-2 rounded-full', statusColors[service.status])} />
              </div>
              <div className="text-xs text-text-secondary">
                <span className={service.status === 'healthy' ? 'text-accent-green' : 'text-accent-yellow'}>
                  {service.status}
                </span>
                {service.latencyMs && <span className="ml-2">{service.latencyMs}ms</span>}
              </div>
              {service.message && (
                <div className="text-xs text-accent-yellow mt-1">{service.message}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Connection Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div data-testid="websocket-status" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <h3 className="text-lg font-semibold mb-4 text-text-primary">WebSocket</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-text-secondary">Status</span>
              <span className={health.websocket.connected ? 'text-accent-green' : 'text-accent-red'}>
                {health.websocket.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Last Message</span>
              <span className="text-text-primary">
                {health.websocket.lastMessageAt
                  ? formatDistanceToNow(new Date(health.websocket.lastMessageAt), { addSuffix: true })
                  : 'Never'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Subscriptions</span>
              <span className="text-text-primary">{health.websocket.subscriptions}</span>
            </div>
          </div>
        </div>

        <div data-testid="database-status" className="bg-bg-secondary rounded-lg p-4 border border-border">
          <h3 className="text-lg font-semibold mb-4 text-text-primary">Database</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-text-secondary">Status</span>
              <span className={health.database.connected ? 'text-accent-green' : 'text-accent-red'}>
                {health.database.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Latency</span>
              <span className="text-text-primary">{health.database.latencyMs}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Connections</span>
              <span className="text-text-primary">{health.database.activeConnections}/{health.database.poolSize}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Rate Limits */}
      <div data-testid="rate-limits" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <h3 className="text-lg font-semibold mb-4 text-text-primary">Rate Limits</h3>
        <div className="space-y-4">
          {health.rateLimits.map((limit) => (
            <div key={limit.endpoint}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-text-primary">{limit.endpoint}</span>
                <span className="text-text-secondary">{limit.remaining}/{limit.limit}</span>
              </div>
              <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
                <div
                  role="progressbar"
                  aria-valuenow={limit.percentUsed}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className={clsx(
                    'h-full rounded-full',
                    limit.percentUsed < 50 ? 'bg-accent-green' :
                    limit.percentUsed < 80 ? 'bg-accent-yellow' : 'bg-accent-red'
                  )}
                  style={{ width: `${limit.percentUsed}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Log Viewer */}
      <div data-testid="log-viewer" className="bg-bg-secondary rounded-lg border border-border overflow-hidden">
        <div data-testid="log-filters" className="flex items-center gap-4 p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <label htmlFor="log-level" className="text-sm text-text-secondary">Level:</label>
            <select
              id="log-level"
              aria-label="Log level filter"
              value={logLevel}
              onChange={(e) => setLogLevel(e.target.value as LogLevel | 'all')}
              className="bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary"
            >
              <option value="all">All</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
            </select>
          </div>

          <input
            type="search"
            role="searchbox"
            placeholder="Search logs..."
            value={logSearch}
            onChange={(e) => setLogSearch(e.target.value)}
            className="flex-1 bg-bg-tertiary border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary"
          />

          <div className="flex items-center gap-2">
            <span className="text-sm text-text-secondary">Auto-scroll</span>
            <button
              role="switch"
              aria-checked={autoScroll}
              aria-label="Toggle auto-scroll"
              onClick={() => setAutoScroll(!autoScroll)}
              className={clsx(
                'relative w-10 h-5 rounded-full transition-colors',
                autoScroll ? 'bg-accent-green' : 'bg-bg-tertiary'
              )}
            >
              <span
                className={clsx(
                  'absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform',
                  autoScroll ? 'left-5' : 'left-0.5'
                )}
              />
            </button>
          </div>
        </div>

        <div ref={logContainerRef} role="log" className="h-64 overflow-y-auto p-4 font-mono text-xs space-y-1">
          {filteredLogs.map((log) => (
            <div key={log.id} className="flex gap-2">
              <span className="text-text-secondary">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className={clsx('uppercase w-16', logLevelColors[log.level])}>
                [{log.level}]
              </span>
              <span className="text-accent-purple">{log.source}</span>
              <span className="text-text-primary">{log.message}</span>
            </div>
          ))}
        </div>
      </div>

      {/* System Configuration */}
      <div data-testid="system-config" className="bg-bg-secondary rounded-lg p-4 border border-border">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">Configuration</h3>
          <button
            onClick={copyConfig}
            className={clsx(
              'px-3 py-1 rounded-lg text-sm transition-colors',
              copySuccess === true ? 'bg-accent-green text-white' :
              copySuccess === false ? 'bg-accent-red text-white' :
              'bg-bg-tertiary text-text-primary hover:bg-bg-tertiary/80'
            )}
          >
            {copySuccess === true ? 'Copied!' : copySuccess === false ? 'Failed' : 'Copy'}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex justify-between">
            <span className="text-text-secondary">Environment</span>
            <span className="text-text-primary capitalize">{config.environment}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Version</span>
            <span className="text-text-primary">{config.version}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Commit</span>
            <span className="text-text-primary font-mono">{config.commitHash}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">API URL</span>
            <span className="text-text-primary">{config.apiBaseUrl}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
