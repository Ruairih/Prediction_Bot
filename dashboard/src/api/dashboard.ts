/**
 * Dashboard API Client
 *
 * Fetches data from the Flask monitoring API and maps snake_case to camelCase.
 */

import type {
  BotStatus,
  DashboardMetrics,
  Position,
  Order,
  ActivityEvent,
  MarketSummary,
  RiskStatus,
  PerformanceStats,
  EquityPoint,
  Trade,
  PnlBucket,
  SystemHealth,
  ServiceStatus,
  SystemConfig,
  LogEntry,
  StrategyConfig,
  Signal,
  MarketDetailResponse,
  MarketOrderbook,
  MarketTrade,
} from '../types';

const API_BASE = '';  // Vite proxy handles /api -> localhost:9050
const API_KEY_STORAGE = 'dashboard_api_key';

/**
 * Convert a camelCase string to snake_case
 * @example camelToSnakeCase('maxPositionSize') => 'max_position_size'
 */
function camelToSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

/**
 * Recursively transform all keys in an object from camelCase to snake_case
 * Handles nested objects and arrays. Does not transform values, only keys.
 */
function transformKeysToSnakeCase<T>(obj: T): unknown {
  if (obj === null || obj === undefined) {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => transformKeysToSnakeCase(item));
  }

  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
      const snakeKey = camelToSnakeCase(key);
      result[snakeKey] = transformKeysToSnakeCase(value);
    }
    return result;
  }

  return obj;
}

function getApiKey(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(API_KEY_STORAGE);
}

async function apiFetch(input: RequestInfo, init: RequestInit = {}) {
  const headers = new Headers(init.headers ?? {});
  const apiKey = getApiKey();
  if (apiKey) {
    headers.set('X-API-Key', apiKey);
  }
  return fetch(input, { ...init, headers });
}

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

interface RawStatus {
  mode: BotStatus['mode'];
  status: BotStatus['status'];
  last_heartbeat: string;
  last_trade_time: string | null;
  error_rate: number;
  websocket_connected: boolean;
  version: string;
}

interface RawRisk {
  current_exposure: number;
  exposure_percent: number;
  balance_health: number;
  limits: {
    max_position_size: number;
    max_total_exposure: number;
    max_positions: number;
    min_balance_reserve: number;
    price_threshold: number;
    stop_loss: number;
    profit_target: number;
    min_hold_days: number;
  };
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

interface RawMarketDetail {
  market: {
    market_id: string | null;
    condition_id: string;
    question: string;
    category: string | null;
    best_bid: number | null;
    best_ask: number | null;
    mid_price: number | null;
    spread: number | null;
    liquidity: number | null;
    volume: number | null;
    end_date: string | null;
    updated_at: string | null;
    model_score?: number | null;
    time_to_end_hours?: number | null;
    filter_rejections?: number | null;
  };
  position: {
    position_id: string;
    token_id: string;
    size: number;
    entry_price: number;
    entry_cost: number;
    current_price: number | null;
    current_value: number | null;
    unrealized_pnl: number | null;
    realized_pnl: number;
    entry_time: string | null;
    status: string | null;
    side: string | null;
    outcome: string | null;
    pnl_percent: number | null;
  } | null;
  orders: Array<{
    order_id: string;
    token_id: string;
    side: string | null;
    price: number;
    size: number;
    status: string | null;
    submitted_at: string | null;
  }>;
  tokens: Array<{
    token_id: string;
    outcome: string | null;
    outcome_index: number | null;
  }>;
  last_signal: {
    token_id: string | null;
    status: string;
    decision: string;
    price: number;
    threshold: number;
    model_score: number | null;
    created_at: string | null;
  } | null;
  last_fill: {
    order_id: string;
    token_id: string;
    side: string | null;
    price: number;
    size: number;
    filled_size: number;
    avg_fill_price: number | null;
    slippage_bps: number | null;
    status: string | null;
    filled_at: string | null;
  } | null;
  last_trade: {
    trade_id: string;
    price: number;
    size: number;
    side: string | null;
    timestamp: string | null;
  } | null;
}

interface RawOrderbook {
  condition_id: string;
  token_id: string | null;
  snapshot_at?: string | null;
  best_bid?: number | null;
  best_ask?: number | null;
  mid_price?: number | null;
  spread?: number | null;
  bids: Array<{ price: number; size: number }>;
  asks: Array<{ price: number; size: number }>;
  depth?: {
    bid: { pct1: number; pct5: number; pct10: number };
    ask: { pct1: number; pct5: number; pct10: number };
  };
  slippage?: {
    buy: Array<{ size: number; avg_price: number | null; slippage_bps: number | null }>;
    sell: Array<{ size: number; avg_price: number | null; slippage_bps: number | null }>;
  };
  source?: string;
}

interface RawOrder {
  order_id: string;
  token_id: string;
  condition_id: string;
  question?: string | null;
  side?: 'BUY' | 'SELL' | null;
  order_price?: number | null;
  order_size?: number | null;
  fill_price?: number | null;
  fill_size?: number | null;
  status: string;
  submitted_at: string;
  filled_at?: string | null;
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


interface RawMarket {
  market_id: string;
  condition_id: string | null;
  question: string;
  category: string | null;
  best_bid: number | null;
  best_ask: number | null;
  volume: number | null;
  liquidity: number | null;
  end_date: string | null;
  generated_at: string | null;
}

interface RawPerformance {
  stats: {
    total_pnl: number;
    win_rate: number;
    total_trades: number;
    sharpe_ratio: number;
    max_drawdown: number;
    max_drawdown_percent: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
    best_trade: number;
    worst_trade: number;
  };
  equity: EquityPoint[];
  trades: Array<{
    trade_id: string;
    position_id: string;
    token_id: string;
    question: string;
    side: Trade['side'];
    size: number;
    entry_price: number;
    exit_price: number;
    pnl: number;
    pnl_percent: number;
    opened_at: string;
    closed_at: string;
    holding_period: number;
    category: string;
  }>;
  pnl: {
    daily: Array<{ period: string; pnl: number; trades: number; wins: number; losses: number }>;
    weekly: Array<{ period: string; pnl: number; trades: number; wins: number; losses: number }>;
    monthly: Array<{ period: string; pnl: number; trades: number; wins: number; losses: number }>;
  };
}

interface RawSystemConfig {
  environment: SystemConfig['environment'];
  version: string;
  commit_hash: string;
  api_base_url: string;
  ws_base_url: string;
  features: Record<string, boolean>;
  uptime: number;
}

/**
 * Fetch health status from /health endpoint
 */
export async function fetchHealth(): Promise<SystemHealth> {
  const response = await apiFetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  const data: RawHealth = await response.json();

  const normalizeStatus = (status: string) => {
    if (status === 'warning') return 'degraded';
    return status as ServiceStatus['status'];
  };

  const services: ServiceStatus[] = data.components.map((c) => ({
    name: c.component,
    status: normalizeStatus(c.status),
    latencyMs: c.latency_ms,
    lastChecked: data.checked_at,
    message: c.message,
  }));

  return {
    overall: normalizeStatus(data.status),
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
  const response = await apiFetch(`${API_BASE}/api/status`);
  if (!response.ok) {
    throw new Error(`Status fetch failed: ${response.status}`);
  }

  const data: RawStatus = await response.json();

  return {
    mode: data.mode,
    status: data.status,
    lastHeartbeat: data.last_heartbeat,
    lastTradeTime: data.last_trade_time,
    errorRate: data.error_rate,
    websocketConnected: data.websocket_connected,
    version: data.version,
  };
}

/**
 * Fetch metrics from /api/metrics endpoint
 */
export async function fetchMetrics(): Promise<DashboardMetrics> {
  const response = await apiFetch(`${API_BASE}/api/metrics`);
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
 * Fetch risk limits and utilization
 */
export async function fetchRisk(): Promise<RiskStatus> {
  const response = await apiFetch(`${API_BASE}/api/risk`);
  if (!response.ok) {
    throw new Error(`Risk fetch failed: ${response.status}`);
  }

  const data: RawRisk = await response.json();

  return {
    currentExposure: data.current_exposure ?? 0,
    exposurePercent: data.exposure_percent ?? 0,
    balanceHealth: data.balance_health ?? 0,
    limits: {
      maxPositionSize: data.limits?.max_position_size ?? 0,
      maxTotalExposure: data.limits?.max_total_exposure ?? 0,
      maxPositions: data.limits?.max_positions ?? 0,
      minBalanceReserve: data.limits?.min_balance_reserve ?? 0,
      priceThreshold: data.limits?.price_threshold ?? 0,
      stopLoss: data.limits?.stop_loss ?? 0,
      profitTarget: data.limits?.profit_target ?? 0,
      minHoldDays: data.limits?.min_hold_days ?? 0,
    },
  };
}

/**
 * Update risk limits
 */
export async function updateRiskLimits(payload: Partial<RiskStatus['limits']>): Promise<RiskStatus> {
  // Transform camelCase keys to snake_case for backend compatibility
  const snakeCasePayload = transformKeysToSnakeCase(payload);
  if (import.meta.env.DEV) {
    console.log('[API] updateRiskLimits payload transformed:', snakeCasePayload);
  }
  const response = await apiFetch(`${API_BASE}/api/risk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snakeCasePayload),
  });
  if (!response.ok) {
    throw new Error(`Risk update failed: ${response.status}`);
  }
  const data: RawRisk = await response.json();
  return {
    currentExposure: data.current_exposure ?? 0,
    exposurePercent: data.exposure_percent ?? 0,
    balanceHealth: data.balance_health ?? 0,
    limits: {
      maxPositionSize: data.limits?.max_position_size ?? 0,
      maxTotalExposure: data.limits?.max_total_exposure ?? 0,
      maxPositions: data.limits?.max_positions ?? 0,
      minBalanceReserve: data.limits?.min_balance_reserve ?? 0,
      priceThreshold: data.limits?.price_threshold ?? 0,
      stopLoss: data.limits?.stop_loss ?? 0,
      profitTarget: data.limits?.profit_target ?? 0,
      minHoldDays: data.limits?.min_hold_days ?? 0,
    },
  };
}

/**
 * Fetch positions from /api/positions endpoint
 */
export async function fetchPositions(): Promise<Position[]> {
  const response = await apiFetch(`${API_BASE}/api/positions`);
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
 * Fetch orders from /api/orders endpoint
 */
export async function fetchOrders(limit = 200): Promise<Order[]> {
  const response = await apiFetch(`${API_BASE}/api/orders?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Orders fetch failed: ${response.status}`);
  }

  const data: { orders: RawOrder[] } = await response.json();

  return (data.orders ?? []).map((order) => ({
    orderId: order.order_id,
    tokenId: order.token_id,
    conditionId: order.condition_id,
    question: order.question ?? `Order ${order.token_id.slice(0, 8)}...`,
    side: (order.side ?? 'BUY') as Order['side'],
    price: order.order_price ?? 0,
    size: order.order_size ?? 0,
    filledSize: order.fill_size ?? 0,
    status: order.status as Order['status'],
    createdAt: order.submitted_at,
    updatedAt: order.filled_at ?? order.submitted_at,
    slippage: order.fill_price && order.order_price
      ? ((order.fill_price - order.order_price) / order.order_price) * 10000
      : undefined,
  }));
}

/**
 * Fetch markets from /api/markets endpoint
 */
export async function fetchMarkets(params?: { limit?: number; q?: string; category?: string }): Promise<MarketSummary[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', String(params.limit));
  if (params?.q) searchParams.set('q', params.q);
  if (params?.category) searchParams.set('category', params.category);

  const url = `${API_BASE}/api/markets${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(`Markets fetch failed: ${response.status}`);
  }

  const data: { markets: RawMarket[] } = await response.json();

  return data.markets.map((market) => {
    const bestBid = market.best_bid ?? null;
    const bestAsk = market.best_ask ?? null;
    const midPrice = bestBid !== null && bestAsk !== null ? (bestBid + bestAsk) / 2 : bestBid ?? bestAsk;
    const spread = bestBid !== null && bestAsk !== null ? bestAsk - bestBid : null;

    return {
      marketId: market.market_id,
      conditionId: market.condition_id ?? null,
      question: market.question,
      category: market.category ?? null,
      bestBid,
      bestAsk,
      midPrice,
      spread,
      volume: market.volume ?? null,
      liquidity: market.liquidity ?? null,
      endDate: market.end_date ?? null,
      updatedAt: market.generated_at ?? null,
    };
  });
}

/**
 * Fetch activity events from /api/activity
 */
export async function fetchActivity(limit = 200): Promise<ActivityEvent[]> {
  const response = await apiFetch(`${API_BASE}/api/activity?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Activity fetch failed: ${response.status}`);
  }

  const data: { events: ActivityEvent[] } = await response.json();
  return data.events ?? [];
}

/**
 * Fetch recent triggers from /api/triggers endpoint
 */
export async function fetchTriggers(limit = 50): Promise<ActivityEvent[]> {
  return fetchActivity(limit);
}

/**
 * Fetch performance summary from /api/performance
 */
export async function fetchPerformance(rangeDays?: number, limit = 200): Promise<{
  stats: PerformanceStats;
  equity: EquityPoint[];
  trades: Trade[];
  pnl: { daily: PnlBucket[]; weekly: PnlBucket[]; monthly: PnlBucket[] };
}> {
  const searchParams = new URLSearchParams();
  if (rangeDays) searchParams.set('range_days', String(rangeDays));
  if (limit) searchParams.set('limit', String(limit));

  const response = await apiFetch(`${API_BASE}/api/performance?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(`Performance fetch failed: ${response.status}`);
  }

  const data: RawPerformance = await response.json();

  return {
    stats: {
      totalPnl: data.stats.total_pnl ?? 0,
      winRate: data.stats.win_rate ?? 0,
      totalTrades: data.stats.total_trades ?? 0,
      sharpeRatio: data.stats.sharpe_ratio ?? 0,
      maxDrawdown: data.stats.max_drawdown ?? 0,
      maxDrawdownPercent: data.stats.max_drawdown_percent ?? 0,
      profitFactor: data.stats.profit_factor ?? 0,
      avgWin: data.stats.avg_win ?? 0,
      avgLoss: data.stats.avg_loss ?? 0,
      bestTrade: data.stats.best_trade ?? 0,
      worstTrade: data.stats.worst_trade ?? 0,
    },
    equity: data.equity ?? [],
    trades: (data.trades ?? []).map((trade) => ({
      tradeId: trade.trade_id,
      positionId: trade.position_id,
      tokenId: trade.token_id,
      question: trade.question,
      side: trade.side,
      size: trade.size,
      entryPrice: trade.entry_price,
      exitPrice: trade.exit_price,
      pnl: trade.pnl,
      pnlPercent: trade.pnl_percent,
      openedAt: trade.opened_at,
      closedAt: trade.closed_at,
      holdingPeriod: trade.holding_period,
      category: trade.category,
    })),
    pnl: {
      daily: (data.pnl?.daily ?? []).map((bucket) => ({
        period: bucket.period,
        pnl: bucket.pnl,
        trades: bucket.trades,
        wins: bucket.wins,
        losses: bucket.losses,
      })),
      weekly: (data.pnl?.weekly ?? []).map((bucket) => ({
        period: bucket.period,
        pnl: bucket.pnl,
        trades: bucket.trades,
        wins: bucket.wins,
        losses: bucket.losses,
      })),
      monthly: (data.pnl?.monthly ?? []).map((bucket) => ({
        period: bucket.period,
        pnl: bucket.pnl,
        trades: bucket.trades,
        wins: bucket.wins,
        losses: bucket.losses,
      })),
    },
  };
}

/**
 * Fetch system configuration
 */
export async function fetchSystemConfig(): Promise<SystemConfig> {
  const response = await apiFetch(`${API_BASE}/api/system`);
  if (!response.ok) {
    throw new Error(`System config fetch failed: ${response.status}`);
  }

  const data: RawSystemConfig = await response.json();
  return {
    environment: data.environment,
    version: data.version,
    commitHash: data.commit_hash,
    apiBaseUrl: data.api_base_url,
    wsBaseUrl: data.ws_base_url,
    features: data.features,
    uptime: data.uptime,
  };
}

/**
 * Fetch log entries
 */
export async function fetchLogs(limit = 200): Promise<LogEntry[]> {
  const response = await apiFetch(`${API_BASE}/api/logs?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Logs fetch failed: ${response.status}`);
  }

  const data: { logs: LogEntry[] } = await response.json();
  return data.logs ?? [];
}

/**
 * Fetch strategy configuration
 */
export async function fetchStrategy(): Promise<StrategyConfig> {
  const response = await apiFetch(`${API_BASE}/api/strategy`);
  if (!response.ok) {
    throw new Error(`Strategy fetch failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch decision log
 */
export async function fetchDecisions(limit = 100): Promise<Signal[]> {
  const response = await apiFetch(`${API_BASE}/api/decisions?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Decisions fetch failed: ${response.status}`);
  }

  const data: { decisions: Signal[] } = await response.json();
  return data.decisions ?? [];
}

/**
 * Fetch market detail
 */
export async function fetchMarketDetail(conditionId: string): Promise<MarketDetailResponse> {
  const response = await apiFetch(`${API_BASE}/api/market/${conditionId}`);
  if (!response.ok) {
    throw new Error(`Market detail fetch failed: ${response.status}`);
  }
  const data: RawMarketDetail = await response.json();

  return {
    market: {
      marketId: data.market.market_id,
      conditionId: data.market.condition_id,
      question: data.market.question,
      category: data.market.category,
      bestBid: data.market.best_bid,
      bestAsk: data.market.best_ask,
      midPrice: data.market.mid_price,
      spread: data.market.spread,
      liquidity: data.market.liquidity,
      volume: data.market.volume,
      endDate: data.market.end_date,
      updatedAt: data.market.updated_at,
      modelScore: data.market.model_score ?? null,
      timeToEndHours: data.market.time_to_end_hours ?? null,
      filterRejections: data.market.filter_rejections ?? null,
    },
    position: data.position
      ? {
          positionId: data.position.position_id,
          tokenId: data.position.token_id,
          size: data.position.size,
          entryPrice: data.position.entry_price,
          entryCost: data.position.entry_cost,
          currentPrice: data.position.current_price,
          currentValue: data.position.current_value,
          unrealizedPnl: data.position.unrealized_pnl,
          realizedPnl: data.position.realized_pnl,
          entryTime: data.position.entry_time,
          status: data.position.status,
          side: data.position.side as 'BUY' | 'SELL' | null,
          outcome: data.position.outcome,
          pnlPercent: data.position.pnl_percent,
        }
      : null,
    orders: (data.orders ?? []).map((order) => ({
      orderId: order.order_id,
      tokenId: order.token_id,
      side: order.side as 'BUY' | 'SELL' | null,
      price: order.price,
      size: order.size,
      status: order.status,
      submittedAt: order.submitted_at,
    })),
    tokens: (data.tokens ?? []).map((token) => ({
      tokenId: token.token_id,
      outcome: token.outcome,
      outcomeIndex: token.outcome_index,
    })),
    lastSignal: data.last_signal
      ? {
          tokenId: data.last_signal.token_id,
          status: data.last_signal.status,
          decision: data.last_signal.decision as 'entry' | 'exit' | 'watch' | 'hold' | 'reject',
          price: data.last_signal.price,
          threshold: data.last_signal.threshold,
          modelScore: data.last_signal.model_score,
          createdAt: data.last_signal.created_at,
        }
      : null,
    lastFill: data.last_fill
      ? {
          orderId: data.last_fill.order_id,
          tokenId: data.last_fill.token_id,
          side: data.last_fill.side as 'BUY' | 'SELL' | null,
          price: data.last_fill.price,
          size: data.last_fill.size,
          filledSize: data.last_fill.filled_size,
          avgFillPrice: data.last_fill.avg_fill_price,
          slippageBps: data.last_fill.slippage_bps,
          status: data.last_fill.status,
          filledAt: data.last_fill.filled_at,
        }
      : null,
    lastTrade: data.last_trade
      ? {
          tradeId: data.last_trade.trade_id,
          price: data.last_trade.price,
          size: data.last_trade.size,
          side: data.last_trade.side,
          timestamp: data.last_trade.timestamp,
        }
      : null,
  };
}

/**
 * Fetch market trade history
 */
export async function fetchMarketHistory(conditionId: string, limit = 200): Promise<MarketTrade[]> {
  const response = await apiFetch(`${API_BASE}/api/market/${conditionId}/history?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Market history fetch failed: ${response.status}`);
  }
  const data: { history: Array<{ trade_id: string; price: number; size: number; side: string; timestamp: string }> } =
    await response.json();
  return (data.history ?? []).map((trade) => ({
    tradeId: trade.trade_id,
    price: trade.price,
    size: trade.size,
    side: trade.side ?? null,
    timestamp: trade.timestamp ?? null,
  }));
}

/**
 * Fetch market orderbook
 */
export async function fetchMarketOrderbook(
  conditionId: string,
  tokenId?: string
): Promise<MarketOrderbook> {
  const params = tokenId ? `?token_id=${encodeURIComponent(tokenId)}` : '';
  const response = await apiFetch(`${API_BASE}/api/market/${conditionId}/orderbook${params}`);
  if (!response.ok) {
    throw new Error(`Market orderbook fetch failed: ${response.status}`);
  }
  const data: RawOrderbook = await response.json();
  // Transform slippage from snake_case to camelCase
  const transformSlippage = (
    items: Array<{ size: number; avg_price: number | null; slippage_bps: number | null }> | undefined
  ) =>
    (items ?? []).map((item) => ({
      size: item.size,
      avgPrice: item.avg_price,
      slippageBps: item.slippage_bps,
    }));

  return {
    conditionId: data.condition_id,
    tokenId: data.token_id ?? null,
    snapshotAt: data.snapshot_at ?? null,
    bestBid: data.best_bid ?? null,
    bestAsk: data.best_ask ?? null,
    midPrice: data.mid_price ?? null,
    spread: data.spread ?? null,
    bids: data.bids ?? [],
    asks: data.asks ?? [],
    depth: data.depth ?? { bid: { pct1: 0, pct5: 0, pct10: 0 }, ask: { pct1: 0, pct5: 0, pct10: 0 } },
    slippage: {
      buy: transformSlippage(data.slippage?.buy),
      sell: transformSlippage(data.slippage?.sell),
    },
    source: data.source ?? 'unavailable',
  };
}

export async function submitManualOrder(payload: {
  tokenId: string;
  side: 'BUY' | 'SELL';
  price: number;
  size: number;
  conditionId?: string;
  reason?: string;
}) {
  // Transform camelCase keys to snake_case for backend compatibility
  const snakeCasePayload = transformKeysToSnakeCase(payload);
  if (import.meta.env.DEV) {
    console.log('[API] submitManualOrder payload transformed:', snakeCasePayload);
  }
  const response = await apiFetch(`${API_BASE}/api/orders/manual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snakeCasePayload),
  });
  if (!response.ok) {
    throw new Error(`Manual order failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Control actions
 */
export async function pauseTrading(reason?: string) {
  const response = await apiFetch(`${API_BASE}/api/control/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(`Pause failed: ${response.status}`);
  }
  return response.json();
}

export async function resumeTrading() {
  const response = await apiFetch(`${API_BASE}/api/control/resume`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Resume failed: ${response.status}`);
  }
  return response.json();
}

export async function killTrading(reason?: string) {
  const response = await apiFetch(`${API_BASE}/api/control/kill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(`Kill failed: ${response.status}`);
  }
  return response.json();
}

export async function cancelAllOrders() {
  const response = await apiFetch(`${API_BASE}/api/orders/cancel_all`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Cancel all orders failed: ${response.status}`);
  }
  return response.json();
}

export async function flattenPositions(reason?: string) {
  const response = await apiFetch(`${API_BASE}/api/positions/flatten`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(`Flatten positions failed: ${response.status}`);
  }
  return response.json();
}

export async function closePosition(positionId: string, price?: number, reason?: string, tokenId?: string) {
  // Transform camelCase keys to snake_case for backend compatibility
  const payload = { price, reason, tokenId };
  const snakeCasePayload = transformKeysToSnakeCase(payload);
  if (import.meta.env.DEV) {
    console.log('[API] closePosition payload transformed:', snakeCasePayload);
  }
  const response = await apiFetch(`${API_BASE}/api/positions/${positionId}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snakeCasePayload),
  });
  if (!response.ok) {
    throw new Error(`Close position failed: ${response.status}`);
  }
  return response.json();
}

export async function blockMarket(conditionId: string, reason?: string, tokenId?: string) {
  // Transform camelCase keys to snake_case for backend compatibility
  const payload = { reason, tokenId };
  const snakeCasePayload = transformKeysToSnakeCase(payload);
  if (import.meta.env.DEV) {
    console.log('[API] blockMarket payload transformed:', snakeCasePayload);
  }
  const response = await apiFetch(`${API_BASE}/api/market/${conditionId}/block`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snakeCasePayload),
  });
  if (!response.ok) {
    throw new Error(`Block market failed: ${response.status}`);
  }
  return response.json();
}

export async function unblockMarket(conditionId: string) {
  const response = await apiFetch(`${API_BASE}/api/market/${conditionId}/block`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(`Unblock market failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Combined dashboard data fetcher
 */
export async function fetchDashboardData() {
  const [status, metrics, positions, activity] = await Promise.all([
    fetchBotStatus().catch(() => null),
    fetchMetrics().catch(() => null),
    fetchPositions().catch(() => []),
    fetchActivity(20).catch(() => []),
  ]);

  return {
    status,
    metrics,
    positions,
    activity,
  };
}

// =============================================================================
// Pipeline Visibility
// =============================================================================

import type {
  PipelineStats,
  PipelineFunnel,
  RejectionEvent,
  CandidateMarket,
  RejectionStage,
} from '../types';

/**
 * Fetch pipeline statistics
 */
export async function fetchPipelineStats(minutes = 60): Promise<PipelineStats> {
  const response = await apiFetch(`${API_BASE}/api/pipeline/stats?minutes=${minutes}`);
  if (!response.ok) {
    throw new Error(`Pipeline stats fetch failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Fetch pipeline funnel summary
 */
export async function fetchPipelineFunnel(minutes = 60): Promise<PipelineFunnel> {
  const response = await apiFetch(`${API_BASE}/api/pipeline/funnel?minutes=${minutes}`);
  if (!response.ok) {
    throw new Error(`Pipeline funnel fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return {
    funnel: data.funnel ?? [],
    totalRejections: data.total_rejections ?? 0,
    minutes: data.minutes ?? minutes,
    samples: data.samples ?? {},
    nearMissCount: data.near_miss_count ?? 0,
    candidateCount: data.candidate_count ?? 0,
  };
}

/**
 * Fetch recent rejections
 */
export async function fetchPipelineRejections(
  limit = 100,
  stage?: RejectionStage
): Promise<RejectionEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (stage) {
    params.set('stage', stage);
  }
  const response = await apiFetch(`${API_BASE}/api/pipeline/rejections?${params}`);
  if (!response.ok) {
    throw new Error(`Pipeline rejections fetch failed: ${response.status}`);
  }
  const data: { rejections: Array<{
    token_id: string;
    condition_id: string;
    stage: RejectionStage;
    timestamp: string;
    price: number;
    question: string;
    trade_size: number | null;
    trade_age_seconds: number | null;
    rejection_values: Record<string, unknown>;
    outcome: string | null;
    rejection_reason: string;
  }> } = await response.json();
  return (data.rejections ?? []).map((r) => ({
    tokenId: r.token_id,
    conditionId: r.condition_id,
    stage: r.stage,
    timestamp: r.timestamp,
    price: r.price,
    question: r.question,
    tradeSize: r.trade_size,
    tradeAgeSeconds: r.trade_age_seconds,
    rejectionValues: r.rejection_values,
    outcome: r.outcome,
    rejectionReason: r.rejection_reason ?? `Rejected at ${r.stage}`,
  }));
}

/**
 * Fetch candidate markets
 */
export async function fetchPipelineCandidates(
  limit = 50,
  sortBy: 'distance' | 'score' | 'recent' = 'distance'
): Promise<CandidateMarket[]> {
  const params = new URLSearchParams({ limit: String(limit), sort: sortBy });
  const response = await apiFetch(`${API_BASE}/api/pipeline/candidates?${params}`);
  if (!response.ok) {
    throw new Error(`Pipeline candidates fetch failed: ${response.status}`);
  }
  const data: { candidates: Array<{
    token_id: string;
    condition_id: string;
    question: string;
    current_price: number;
    threshold: number;
    distance_to_threshold: number;
    last_updated: string;
    last_signal: string;
    last_signal_reason: string;
    model_score: number | null;
    time_to_end_hours: number;
    trade_size: number | null;
    trade_age_seconds: number;
    highest_price_seen: number;
    times_evaluated: number;
    outcome: string | null;
    is_near_miss: boolean;
    is_above_threshold: boolean;
    status_label: string;
  }> } = await response.json();
  return (data.candidates ?? []).map((c) => ({
    tokenId: c.token_id,
    conditionId: c.condition_id,
    question: c.question,
    currentPrice: c.current_price,
    threshold: c.threshold,
    distanceToThreshold: c.distance_to_threshold,
    lastUpdated: c.last_updated,
    lastSignal: c.last_signal,
    lastSignalReason: c.last_signal_reason,
    modelScore: c.model_score,
    timeToEndHours: c.time_to_end_hours,
    tradeSize: c.trade_size,
    tradeAgeSeconds: c.trade_age_seconds,
    highestPriceSeen: c.highest_price_seen,
    timesEvaluated: c.times_evaluated,
    outcome: c.outcome,
    isNearMiss: c.is_near_miss ?? (c.current_price >= c.threshold),
    isAboveThreshold: c.is_above_threshold ?? (c.current_price >= c.threshold),
    statusLabel: c.status_label ?? (c.current_price >= c.threshold ? 'Triggered (Held)' : 'Watching'),
  }));
}

/**
 * Fetch near-miss markets (triggered but strategy held)
 */
export async function fetchNearMisses(maxDistance = 0.02): Promise<CandidateMarket[]> {
  const response = await apiFetch(`${API_BASE}/api/pipeline/near-misses?max_distance=${maxDistance}`);
  if (!response.ok) {
    throw new Error(`Near misses fetch failed: ${response.status}`);
  }
  const data: { near_misses: Array<{
    token_id: string;
    condition_id: string;
    question: string;
    current_price: number;
    threshold: number;
    distance_to_threshold: number;
    last_updated: string;
    last_signal: string;
    last_signal_reason: string;
    model_score: number | null;
    time_to_end_hours: number;
    trade_size: number | null;
    trade_age_seconds: number;
    highest_price_seen: number;
    times_evaluated: number;
    outcome: string | null;
    is_near_miss: boolean;
    is_above_threshold: boolean;
    status_label: string;
  }> } = await response.json();
  return (data.near_misses ?? []).map((c) => ({
    tokenId: c.token_id,
    conditionId: c.condition_id,
    question: c.question,
    currentPrice: c.current_price,
    threshold: c.threshold,
    distanceToThreshold: c.distance_to_threshold,
    lastUpdated: c.last_updated,
    lastSignal: c.last_signal,
    lastSignalReason: c.last_signal_reason,
    modelScore: c.model_score,
    timeToEndHours: c.time_to_end_hours,
    tradeSize: c.trade_size,
    tradeAgeSeconds: c.trade_age_seconds,
    highestPriceSeen: c.highest_price_seen,
    timesEvaluated: c.times_evaluated,
    outcome: c.outcome,
    isNearMiss: c.is_near_miss ?? true,
    isAboveThreshold: c.is_above_threshold ?? true,
    statusLabel: c.status_label ?? 'Triggered (Held)',
  }));
}
