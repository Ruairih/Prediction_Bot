/**
 * Dashboard API Client
 *
 * Fetches data from the Flask monitoring API and maps snake_case to camelCase.
 */

import type {
  BotStatus,
  DashboardMetrics,
  Position,
  ActivityEvent,
  SystemHealth,
  ServiceStatus,
} from '../types';

const API_BASE = '';  // Vite proxy handles /api -> localhost:5050

/**
 * Raw API response types (snake_case from Flask)
 */
interface RawMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  position_count: number;
  capital_deployed: number;
  available_balance: number;
  calculated_at: string;
}

interface RawPosition {
  position_id: string;
  token_id: string;
  condition_id: string;
  size: number;
  entry_price: number;
  entry_cost: number;
  entry_time: string;
  current_price?: number;
  unrealized_pnl?: number;
  realized_pnl: number;
  status: string;
  description?: string;
}

interface RawHealthComponent {
  component: string;
  status: string;
  message: string;
  latency_ms: number | null;
}

interface RawHealth {
  status: string;
  components: RawHealthComponent[];
  checked_at: string;
}

interface RawTrigger {
  token_id: string;
  condition_id: string;
  threshold: number | null;
  price: number | null;
  trade_size: number | null;
  model_score: number | null;
  triggered_at: string;
}

/**
 * Fetch health status from /health endpoint
 */
export async function fetchHealth(): Promise<SystemHealth> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  const data: RawHealth = await response.json();

  const services: ServiceStatus[] = data.components.map((c) => ({
    name: c.component,
    status: c.status as 'healthy' | 'degraded' | 'unhealthy' | 'unknown',
    latencyMs: c.latency_ms,
    lastChecked: data.checked_at,
    message: c.message,
  }));

  return {
    overall: data.status as 'healthy' | 'degraded' | 'unhealthy' | 'unknown',
    services,
    websocket: {
      connected: services.some((s) => s.name === 'websocket' && s.status === 'healthy'),
      lastMessageAt: null,
      reconnectAttempts: 0,
      subscriptions: 0,
    },
    database: {
      connected: services.some((s) => s.name === 'database' && s.status === 'healthy'),
      latencyMs: services.find((s) => s.name === 'database')?.latencyMs ?? 0,
      poolSize: 10,
      activeConnections: 1,
    },
    rateLimits: [],
    uptime: 0,
    lastHealthCheck: data.checked_at,
  };
}

/**
 * Fetch bot status (derived from health)
 */
export async function fetchBotStatus(): Promise<BotStatus> {
  try {
    const health = await fetchHealth();

    return {
      mode: 'dry_run',  // TODO: Get from API
      status: health.overall as 'healthy' | 'degraded' | 'unhealthy',
      lastHeartbeat: health.lastHealthCheck,
      lastTradeTime: null,
      errorRate: 0,
      websocketConnected: health.websocket.connected,
      version: '1.0.0',
    };
  } catch {
    return {
      mode: 'stopped',
      status: 'unhealthy',
      lastHeartbeat: new Date().toISOString(),
      lastTradeTime: null,
      errorRate: 1,
      websocketConnected: false,
      version: '1.0.0',
    };
  }
}

/**
 * Fetch metrics from /api/metrics endpoint
 */
export async function fetchMetrics(): Promise<DashboardMetrics> {
  const response = await fetch(`${API_BASE}/api/metrics`);
  if (!response.ok) {
    throw new Error(`Metrics fetch failed: ${response.status}`);
  }

  const data: RawMetrics = await response.json();

  return {
    totalPnl: data.total_pnl ?? 0,
    todayPnl: 0,  // TODO: Calculate from daily_pnl table
    winRate: data.win_rate ?? 0,
    totalTrades: data.total_trades ?? 0,
    winningTrades: data.winning_trades ?? 0,
    losingTrades: data.losing_trades ?? 0,
    openPositions: data.position_count ?? 0,
    availableBalance: data.available_balance ?? 0,
    capitalDeployed: data.capital_deployed ?? 0,
    calculatedAt: data.calculated_at ?? new Date().toISOString(),
  };
}

/**
 * Fetch positions from /api/positions endpoint
 */
export async function fetchPositions(): Promise<Position[]> {
  const response = await fetch(`${API_BASE}/api/positions`);
  if (!response.ok) {
    throw new Error(`Positions fetch failed: ${response.status}`);
  }

  const data: { positions: RawPosition[] } = await response.json();

  return data.positions.map((p) => {
    const entryCost = p.entry_cost ?? p.entry_price * p.size;
    const currentPrice = p.current_price ?? p.entry_price;
    const unrealizedPnl = p.unrealized_pnl ?? (currentPrice - p.entry_price) * p.size;
    const pnlPercent = entryCost > 0 ? (unrealizedPnl / entryCost) * 100 : 0;
    const entryTime = new Date(p.entry_time);
    const holdingDays = Math.floor((Date.now() - entryTime.getTime()) / (1000 * 60 * 60 * 24));

    return {
      positionId: p.position_id,
      tokenId: p.token_id,
      conditionId: p.condition_id,
      question: p.description ?? `Position ${p.token_id.slice(0, 8)}...`,
      size: p.size,
      entryPrice: p.entry_price,
      currentPrice,
      entryCost,
      unrealizedPnl,
      pnlPercent,
      entryTime: p.entry_time,
      holdingDays,
      status: p.status as 'open' | 'closed' | 'pending_close',
    };
  });
}

/**
 * Fetch recent triggers from /api/triggers endpoint
 */
export async function fetchTriggers(limit = 50): Promise<ActivityEvent[]> {
  const response = await fetch(`${API_BASE}/api/triggers?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Triggers fetch failed: ${response.status}`);
  }

  const data: { triggers: RawTrigger[] } = await response.json();

  return data.triggers.map((t, index) => ({
    id: `trigger-${index}-${t.triggered_at}`,
    type: 'signal' as const,
    timestamp: t.triggered_at,
    summary: `Trigger @ $${t.price?.toFixed(2) ?? '?'} (size: ${t.trade_size ?? '?'})`,
    details: {
      tokenId: t.token_id,
      conditionId: t.condition_id,
      threshold: t.threshold,
      price: t.price,
      tradeSize: t.trade_size,
      modelScore: t.model_score,
    },
    severity: 'info' as const,
  }));
}

/**
 * Combined dashboard data fetcher
 */
export async function fetchDashboardData() {
  const [status, metrics, positions, activity] = await Promise.all([
    fetchBotStatus().catch(() => null),
    fetchMetrics().catch(() => null),
    fetchPositions().catch(() => []),
    fetchTriggers(20).catch(() => []),
  ]);

  return {
    status,
    metrics,
    positions,
    activity,
  };
}
