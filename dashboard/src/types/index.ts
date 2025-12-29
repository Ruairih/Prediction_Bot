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
// Markets
// =============================================================================

export interface MarketSummary {
  marketId: string;
  conditionId: string | null;
  question: string;
  category: string | null;
  bestBid: number | null;
  bestAsk: number | null;
  midPrice: number | null;
  spread: number | null;
  volume: number | null;
  liquidity: number | null;
  endDate: string | null;
  updatedAt: string | null;
}

export interface MarketToken {
  tokenId: string;
  outcome: string | null;
  outcomeIndex: number | null;
}

export interface MarketDetailMarket {
  marketId: string | null;
  conditionId: string;
  question: string;
  category: string | null;
  bestBid: number | null;
  bestAsk: number | null;
  midPrice: number | null;
  spread: number | null;
  liquidity: number | null;
  volume: number | null;
  endDate: string | null;
  updatedAt: string | null;
  modelScore: number | null;
  timeToEndHours: number | null;
  filterRejections: number | null;
}

export interface MarketDetailPosition {
  positionId: string;
  tokenId: string;
  size: number;
  entryPrice: number;
  entryCost: number;
  currentPrice: number | null;
  currentValue: number | null;
  unrealizedPnl: number | null;
  realizedPnl: number;
  entryTime: string | null;
  status: string | null;
  side: OrderSide | null;
  outcome: string | null;
  pnlPercent: number | null;
}

export interface MarketOpenOrder {
  orderId: string;
  tokenId: string;
  side: OrderSide | null;
  price: number;
  size: number;
  status: string | null;
  submittedAt: string | null;
}

export interface MarketSignal {
  tokenId: string | null;
  status: string;
  decision: SignalDecision;
  price: number;
  threshold: number;
  modelScore: number | null;
  createdAt: string | null;
}

export interface MarketFill {
  orderId: string;
  tokenId: string;
  side: OrderSide | null;
  price: number;
  size: number;
  filledSize: number;
  avgFillPrice: number | null;
  slippageBps: number | null;
  status: string | null;
  filledAt: string | null;
}

export interface MarketTrade {
  tradeId: string;
  price: number;
  size: number;
  side: string | null;
  timestamp: string | null;
}

export interface MarketDetailResponse {
  market: MarketDetailMarket;
  position: MarketDetailPosition | null;
  orders: MarketOpenOrder[];
  tokens: MarketToken[];
  lastSignal: MarketSignal | null;
  lastFill: MarketFill | null;
  lastTrade: MarketTrade | null;
}

export interface OrderbookLevel {
  price: number;
  size: number;
}

export interface OrderbookDepth {
  pct1: number;
  pct5: number;
  pct10: number;
}

export interface OrderbookSlippage {
  size: number;
  avgPrice: number | null;
  slippageBps: number | null;
}

export interface MarketOrderbook {
  conditionId: string;
  tokenId: string | null;
  snapshotAt: string | null;
  bestBid: number | null;
  bestAsk: number | null;
  midPrice: number | null;
  spread: number | null;
  bids: OrderbookLevel[];
  asks: OrderbookLevel[];
  depth: {
    bid: OrderbookDepth;
    ask: OrderbookDepth;
  };
  slippage: {
    buy: OrderbookSlippage[];
    sell: OrderbookSlippage[];
  };
  source: string;
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
  maxPriceDeviation?: number;
  maxTradeAgeSeconds?: number;
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

export interface PerformanceResponse {
  stats: PerformanceStats;
  equity: EquityPoint[];
  trades: Trade[];
  pnl: {
    daily: PnlBucket[];
    weekly: PnlBucket[];
    monthly: PnlBucket[];
  };
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
  uptime?: number;
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

// =============================================================================
// Pipeline Visibility
// =============================================================================

export type RejectionStage =
  | 'threshold'
  | 'duplicate'
  | 'g1_trade_age'
  | 'g5_orderbook'
  | 'g6_weather'
  | 'time_to_end'
  | 'trade_size'
  | 'category'
  | 'manual_block'
  | 'max_positions'
  | 'strategy_hold'
  | 'strategy_ignore';

export interface RejectionEvent {
  tokenId: string;
  conditionId: string;
  stage: RejectionStage;
  timestamp: string;
  price: number;
  question: string;
  tradeSize: number | null;
  tradeAgeSeconds: number | null;
  rejectionValues: Record<string, unknown>;
  outcome: string | null;  // "Yes" or "No" - direction of the trade
  rejectionReason: string;  // Human-readable explanation of why rejected
}

export interface CandidateMarket {
  tokenId: string;
  conditionId: string;
  question: string;
  currentPrice: number;
  threshold: number;
  distanceToThreshold: number;  // Negative if above threshold
  lastUpdated: string;
  lastSignal: string;
  lastSignalReason: string;
  modelScore: number | null;
  timeToEndHours: number;
  tradeSize: number | null;
  tradeAgeSeconds: number;
  highestPriceSeen: number;
  timesEvaluated: number;
  outcome: string | null;  // "Yes" or "No" - which outcome token this is
  isNearMiss: boolean;  // True if triggered (price >= threshold)
  isAboveThreshold: boolean;  // True if price >= threshold
  statusLabel: string;  // "Triggered (Held)", "Very Close", or "Watching"
}

export interface PipelineStats {
  totals: Record<RejectionStage, number>;
  total: number;
  since?: string;
  minutes?: number;
}

export interface FunnelItem {
  stage: RejectionStage;
  label: string;
  count: number;
  percentage: number;
}

export interface PipelineFunnel {
  funnel: FunnelItem[];
  totalRejections: number;
  minutes: number;
  samples: Record<RejectionStage, RejectionEvent[]>;
  nearMissCount: number;
  candidateCount: number;
}
