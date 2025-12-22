/**
 * Dashboard Type Definitions
 *
 * These types define the data contracts between frontend and API.
 * Written FIRST as part of TDD - tests will use these types.
 */

// =============================================================================
// Bot Status & Mode
// =============================================================================

export type BotMode = 'live' | 'dry_run' | 'paused' | 'stopped';
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export interface BotStatus {
  mode: BotMode;
  status: HealthStatus;
  lastHeartbeat: string;
  lastTradeTime: string | null;
  errorRate: number;
  websocketConnected: boolean;
  version: string;
}

// =============================================================================
// Metrics & KPIs
// =============================================================================

export interface DashboardMetrics {
  totalPnl: number;
  todayPnl: number;
  winRate: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  openPositions: number;
  availableBalance: number;
  capitalDeployed: number;
  calculatedAt: string;
}

// =============================================================================
// Positions
// =============================================================================

export type PositionStatus = 'open' | 'closed' | 'pending_close';

export interface Position {
  positionId: string;
  tokenId: string;
  conditionId: string;
  question: string;
  size: number;
  entryPrice: number;
  currentPrice: number;
  entryCost: number;
  unrealizedPnl: number;
  pnlPercent: number;
  entryTime: string;
  holdingDays: number;
  status: PositionStatus;
}

// =============================================================================
// Orders
// =============================================================================

export type OrderSide = 'BUY' | 'SELL';
export type OrderStatus = 'pending' | 'live' | 'partial' | 'filled' | 'cancelled' | 'failed';

export interface Order {
  orderId: string;
  tokenId: string;
  conditionId: string;
  question: string;
  side: OrderSide;
  price: number;
  size: number;
  filledSize: number;
  status: OrderStatus;
  createdAt: string;
  updatedAt: string;
  slippage?: number;
}

// =============================================================================
// Signals & Decisions
// =============================================================================

export type SignalDecision = 'entry' | 'exit' | 'watch' | 'hold' | 'reject';

export interface Signal {
  id: string;
  marketId: string;
  tokenId: string;
  question: string;
  timestamp: string;
  triggerPrice: number;
  tradeSize: number | null;
  modelScore: number | null;
  decision: SignalDecision;
  reason: string;
  filters: {
    g1Passed: boolean;  // Trade age filter
    g5Passed: boolean;  // Orderbook verification
    g6Passed: boolean;  // Weather filter
    sizePassed: boolean;
  };
}

// =============================================================================
// Activity Log
// =============================================================================

export type ActivityType =
  | 'price_update'
  | 'signal'
  | 'order_submitted'
  | 'order_filled'
  | 'order_cancelled'
  | 'position_opened'
  | 'position_closed'
  | 'bot_state_change'
  | 'alert'
  | 'error';

export interface ActivityEvent {
  id: string;
  type: ActivityType;
  timestamp: string;
  summary: string;
  details: Record<string, unknown>;
  severity: 'info' | 'success' | 'warning' | 'error';
}

// =============================================================================
// Performance
// =============================================================================

export interface DailyPerformance {
  date: string;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
  cumulativePnl: number;
}

export interface PerformanceByCategory {
  category: string;
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  pnl: number;
}

// =============================================================================
// Risk & Limits
// =============================================================================

export interface RiskLimits {
  maxPositionSize: number;
  maxTotalExposure: number;
  maxPositions: number;
  minBalanceReserve: number;
  priceThreshold: number;
  stopLoss: number;
  profitTarget: number;
  minHoldDays: number;
}

export interface RiskStatus {
  currentExposure: number;
  exposurePercent: number;
  balanceHealth: number;
  limits: RiskLimits;
}

// =============================================================================
// WebSocket Events
// =============================================================================

export type WebSocketEventType =
  | 'price'
  | 'signal'
  | 'order'
  | 'fill'
  | 'position'
  | 'bot_state'
  | 'alert'
  | 'metrics';

export interface WebSocketEvent<T = unknown> {
  type: WebSocketEventType;
  timestamp: string;
  data: T;
}

// =============================================================================
// Positions - Extended
// =============================================================================

export interface PositionSummary {
  openCount: number;
  totalExposure: number;
  totalUnrealizedPnl: number;
  totalRealizedPnl: number;
}

export interface PositionFilterState {
  status: PositionStatus | 'all';
  pnl: 'all' | 'profitable' | 'losing';
  search: string;
  sortBy: 'entryTime' | 'unrealizedPnl' | 'size' | 'pnlPercent';
  sortDir: 'asc' | 'desc';
}

export interface PositionDetail extends Position {
  realizedPnl: number;
  expiry: string | null;
  side: OrderSide;
  category: string;
  orders: Order[];
}

// =============================================================================
// Activity - Extended
// =============================================================================

export interface ActivityFilterState {
  types: ActivityType[];
  severities: Array<'info' | 'success' | 'warning' | 'error'>;
  startDate: string | null;
  endDate: string | null;
  search: string;
}

export interface ActivityStats {
  total: number;
  byType: Record<ActivityType, number>;
  bySeverity: Record<string, number>;
}

// =============================================================================
// Performance - Extended
// =============================================================================

export type TimeRange = '1d' | '7d' | '30d' | '90d' | 'all';

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface PerformanceStats {
  totalPnl: number;
  winRate: number;
  totalTrades: number;
  sharpeRatio: number;
  maxDrawdown: number;
  maxDrawdownPercent: number;
  profitFactor: number;
  avgWin: number;
  avgLoss: number;
  bestTrade: number;
  worstTrade: number;
}

export interface PnlBucket {
  period: string;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
}

export interface Trade {
  tradeId: string;
  positionId: string;
  tokenId: string;
  question: string;
  side: OrderSide;
  size: number;
  entryPrice: number;
  exitPrice: number | null;
  pnl: number;
  pnlPercent: number;
  openedAt: string;
  closedAt: string | null;
  holdingPeriod: number;
  category: string;
}

// =============================================================================
// Strategy
// =============================================================================

export type ParameterType = 'number' | 'boolean' | 'string' | 'select';

export interface StrategyParameter {
  key: string;
  label: string;
  type: ParameterType;
  value: number | boolean | string;
  defaultValue: number | boolean | string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  unit?: string;
  description?: string;
}

export interface FilterConfig {
  blockedCategories: string[];
  weatherFilterEnabled: boolean;
  minTradeSize: number;
  maxTradeAge: number;
  minTimeToExpiry: number;
  maxPriceDeviation: number;
}

export interface StrategyConfig {
  name: string;
  version: string;
  enabled: boolean;
  parameters: StrategyParameter[];
  filters: FilterConfig;
  lastModified: string;
}

export interface BacktestRequest {
  startDate: string;
  endDate: string;
  initialBalance: number;
}

export interface BacktestResult {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  period: { start: string; end: string };
  trades: number;
  winRate: number;
  pnl: number;
  sharpeRatio: number;
  maxDrawdown: number;
  equitySeries: EquityPoint[];
  createdAt: string;
  completedAt: string | null;
}

// =============================================================================
// Risk - Extended
// =============================================================================

export interface ExposureMetric {
  currentExposure: number;
  maxExposure: number;
  exposurePercent: number;
  leverage: number;
}

export interface ExposureByCategory {
  category: string;
  exposure: number;
  positionCount: number;
  pnl: number;
  riskLevel: 'low' | 'medium' | 'high';
}

export interface CorrelationCell {
  categoryA: string;
  categoryB: string;
  correlation: number;
}

export interface RiskAlert {
  id: string;
  type: 'drawdown' | 'exposure' | 'position_size' | 'loss_streak';
  threshold: number;
  currentValue: number;
  message: string;
  triggeredAt: string;
  acknowledged: boolean;
}

// =============================================================================
// System
// =============================================================================

export type ServiceStatusValue = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

export interface ServiceStatus {
  name: string;
  status: ServiceStatusValue;
  latencyMs: number | null;
  lastChecked: string;
  message?: string;
}

export interface WebSocketStatus {
  connected: boolean;
  lastMessageAt: string | null;
  reconnectAttempts: number;
  subscriptions: number;
}

export interface DatabaseStatus {
  connected: boolean;
  latencyMs: number;
  poolSize: number;
  activeConnections: number;
}

export interface RateLimitStatus {
  endpoint: string;
  limit: number;
  remaining: number;
  resetAt: string;
  percentUsed: number;
}

export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  source: string;
  message: string;
  context?: Record<string, unknown>;
}

export interface SystemConfig {
  environment: 'development' | 'staging' | 'production';
  version: string;
  commitHash: string;
  apiBaseUrl: string;
  wsBaseUrl: string;
  features: Record<string, boolean>;
}

export interface SystemHealth {
  overall: ServiceStatusValue;
  services: ServiceStatus[];
  websocket: WebSocketStatus;
  database: DatabaseStatus;
  rateLimits: RateLimitStatus[];
  uptime: number;
  lastHealthCheck: string;
}

// =============================================================================
// API Response Wrappers
// =============================================================================

export interface ApiResponse<T> {
  data: T;
  error?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}
