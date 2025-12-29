import type { Page } from '@playwright/test';

type MockData = {
  status: Record<string, unknown>;
  metrics: Record<string, unknown>;
  health: Record<string, unknown>;
  positions: Record<string, unknown>;
  orders: Record<string, unknown>;
  activity: Record<string, unknown>;
  risk: Record<string, unknown>;
  performance: Record<string, unknown>;
  markets: Record<string, unknown>;
  marketDetail: Record<string, unknown>;
  marketHistory: Record<string, unknown>;
  marketOrderbook: Record<string, unknown>;
  strategy: Record<string, unknown>;
  system: Record<string, unknown>;
  logs: Record<string, unknown>;
  decisions: Record<string, unknown>;
  pipelineFunnel: Record<string, unknown>;
  pipelineRejections: Record<string, unknown>;
  pipelineCandidates: Record<string, unknown>;
  nearMisses: Record<string, unknown>;
  pipelineStats: Record<string, unknown>;
};

function buildMockData(overrides: Partial<MockData> = {}): MockData {
  const now = Date.now();
  const isoNow = new Date(now).toISOString();

  const base: MockData = {
    status: {
      mode: 'dry_run',
      status: 'healthy',
      last_heartbeat: isoNow,
      last_trade_time: null,
      error_rate: 0,
      websocket_connected: true,
      version: '1.0.0',
    },
    metrics: {
      total_trades: 42,
      winning_trades: 30,
      losing_trades: 12,
      win_rate: 0.714,
      total_pnl: 125.5,
      realized_pnl: 125.5,
      unrealized_pnl: 0,
      position_count: 5,
      capital_deployed: 300,
      available_balance: 500,
      calculated_at: isoNow,
    },
    health: {
      status: 'healthy',
      components: [
        { component: 'database', status: 'healthy', message: 'OK', latency_ms: 5 },
        { component: 'websocket', status: 'healthy', message: 'Connected', latency_ms: 10 },
        { component: 'ingestion', status: 'healthy', message: 'Streaming', latency_ms: 12 },
      ],
      checked_at: isoNow,
    },
    positions: {
      positions: [
        {
          position_id: 'pos_1',
          token_id: 'tok_abc123',
          condition_id: 'cond_xyz',
          size: 20,
          entry_price: 0.95,
          entry_cost: 19,
          entry_time: new Date(now - 86400000 * 3).toISOString(),
          current_price: 0.97,
          unrealized_pnl: 0.4,
          realized_pnl: 0,
          status: 'open',
          description: 'Will Bitcoin reach $100k by end of 2024?',
        },
        {
          position_id: 'pos_2',
          token_id: 'tok_def456',
          condition_id: 'cond_uvw',
          size: 15,
          entry_price: 0.92,
          entry_cost: 13.8,
          entry_time: new Date(now - 86400000 * 7).toISOString(),
          current_price: 0.88,
          unrealized_pnl: -0.6,
          realized_pnl: 0,
          status: 'open',
          description: 'Will there be a government shutdown in January 2025?',
        },
      ],
    },
    orders: {
      orders: [
        {
          order_id: 'ord_1',
          token_id: 'tok_abc123',
          condition_id: 'cond_xyz',
          side: 'BUY',
          order_price: 0.95,
          order_size: 20,
          fill_price: 0.951,
          fill_size: 20,
          status: 'filled',
          submitted_at: new Date(now - 3600000).toISOString(),
          filled_at: new Date(now - 3598000).toISOString(),
        },
        {
          order_id: 'ord_2',
          token_id: 'tok_def456',
          condition_id: 'cond_uvw',
          side: 'SELL',
          order_price: 0.88,
          order_size: 10,
          fill_price: null,
          fill_size: 0,
          status: 'cancelled',
          submitted_at: new Date(now - 7200000).toISOString(),
          filled_at: null,
        },
      ],
    },
    activity: {
      events: [
        {
          id: 'evt_1',
          type: 'order_filled',
          timestamp: isoNow,
          summary: 'Order filled: BUY 20 shares at $0.95',
          details: { orderId: 'ord_1', price: 0.95, size: 20, conditionId: 'cond_xyz' },
          severity: 'success',
        },
        {
          id: 'evt_2',
          type: 'signal',
          timestamp: new Date(now - 3600000).toISOString(),
          summary: 'Signal detected: BTC market triggered at $0.96',
          details: { tokenId: 'tok_abc', price: 0.96, conditionId: 'cond_xyz' },
          severity: 'info',
        },
        {
          id: 'evt_3',
          type: 'alert',
          timestamp: new Date(now - 7200000).toISOString(),
          summary: 'Low balance warning',
          details: { balance: 50 },
          severity: 'warning',
        },
      ],
    },
    risk: {
      current_exposure: 300,
      exposure_percent: 75,
      balance_health: 0.9,
      limits: {
        max_position_size: 20,
        max_total_exposure: 500,
        max_positions: 50,
        min_balance_reserve: 100,
        price_threshold: 0.95,
        stop_loss: 0.9,
        profit_target: 0.99,
        min_hold_days: 7,
      },
    },
    performance: {
      stats: {
        total_pnl: 125.5,
        win_rate: 0.714,
        total_trades: 42,
        sharpe_ratio: 1.25,
        max_drawdown: 50,
        max_drawdown_percent: 10,
        profit_factor: 2.5,
        avg_win: 5.25,
        avg_loss: 3.1,
        best_trade: 15.0,
        worst_trade: -8.5,
      },
      equity: [
        { timestamp: '2024-12-01', equity: 0 },
        { timestamp: '2024-12-05', equity: 25 },
        { timestamp: '2024-12-10', equity: 50 },
        { timestamp: '2024-12-15', equity: 75 },
        { timestamp: '2024-12-20', equity: 100 },
        { timestamp: '2024-12-25', equity: 125.5 },
      ],
      trades: [
        {
          trade_id: 'trade_1',
          position_id: 'pos_closed_1',
          token_id: 'tok_old1',
          question: 'Will the Fed raise rates in December 2024?',
          side: 'BUY',
          size: 20,
          entry_price: 0.8,
          exit_price: 1.0,
          pnl: 4.0,
          pnl_percent: 25,
          opened_at: '2024-12-01T10:00:00Z',
          closed_at: '2024-12-05T14:00:00Z',
          holding_period: 4,
          category: 'Economics',
        },
        {
          trade_id: 'trade_2',
          position_id: 'pos_closed_2',
          token_id: 'tok_old2',
          question: 'Will Bitcoin hit $50k in November 2024?',
          side: 'BUY',
          size: 15,
          entry_price: 0.9,
          exit_price: 0.0,
          pnl: -13.5,
          pnl_percent: -100,
          opened_at: '2024-11-20T10:00:00Z',
          closed_at: '2024-11-30T14:00:00Z',
          holding_period: 10,
          category: 'Crypto',
        },
      ],
      pnl: {
        daily: [
          { period: '2024-12-20', pnl: 10.5, trades: 2, wins: 2, losses: 0 },
          { period: '2024-12-21', pnl: -5.0, trades: 1, wins: 0, losses: 1 },
          { period: '2024-12-22', pnl: 15.0, trades: 3, wins: 2, losses: 1 },
        ],
        weekly: [
          { period: '2024-W50', pnl: 45.0, trades: 8, wins: 6, losses: 2 },
          { period: '2024-W51', pnl: 30.5, trades: 6, wins: 4, losses: 2 },
        ],
        monthly: [
          { period: '2024-11', pnl: 50.0, trades: 20, wins: 14, losses: 6 },
          { period: '2024-12', pnl: 75.5, trades: 22, wins: 16, losses: 6 },
        ],
      },
    },
    markets: {
      markets: [
        {
          market_id: 'mkt_1',
          condition_id: 'cond_xyz',
          question: 'Will Bitcoin reach $100k by end of 2024?',
          category: 'Crypto',
          best_bid: 0.45,
          best_ask: 0.47,
          volume: 50000,
          liquidity: 25000,
          end_date: '2024-12-31T23:59:59Z',
          generated_at: isoNow,
        },
        {
          market_id: 'mkt_2',
          condition_id: 'cond_uvw',
          question: 'Will there be a government shutdown?',
          category: 'Politics',
          best_bid: 0.32,
          best_ask: 0.35,
          volume: 30000,
          liquidity: 15000,
          end_date: '2025-01-15T23:59:59Z',
          generated_at: isoNow,
        },
      ],
    },
    marketDetail: {
      market: {
        market_id: 'mkt_1',
        condition_id: 'cond_xyz',
        question: 'Will Bitcoin reach $100k by end of 2024?',
        category: 'Crypto',
        best_bid: 0.45,
        best_ask: 0.47,
        mid_price: 0.46,
        spread: 0.02,
        liquidity: 25000,
        volume: 50000,
        end_date: '2024-12-31T23:59:59Z',
        updated_at: isoNow,
        model_score: 0.92,
        time_to_end_hours: 120,
        filter_rejections: 2,
      },
      position: null,
      orders: [],
      tokens: [
        { token_id: 'tok_abc123', outcome: 'Yes', outcome_index: 0 },
        { token_id: 'tok_def456', outcome: 'No', outcome_index: 1 },
      ],
      last_signal: null,
      last_fill: null,
      last_trade: null,
    },
    marketHistory: {
      history: [
        {
          trade_id: 'trade_1',
          price: 0.45,
          size: 120,
          side: 'BUY',
          timestamp: new Date(now - 3600000).toISOString(),
        },
        {
          trade_id: 'trade_2',
          price: 0.46,
          size: 80,
          side: 'SELL',
          timestamp: new Date(now - 1800000).toISOString(),
        },
      ],
    },
    marketOrderbook: {
      condition_id: 'cond_xyz',
      token_id: 'tok_abc123',
      snapshot_at: isoNow,
      best_bid: 0.45,
      best_ask: 0.47,
      mid_price: 0.46,
      spread: 0.02,
      bids: [{ price: 0.45, size: 100 }],
      asks: [{ price: 0.47, size: 120 }],
      depth: {
        bid: { pct1: 200, pct5: 500, pct10: 800 },
        ask: { pct1: 180, pct5: 450, pct10: 700 },
      },
      slippage: {
        buy: [{ size: 50, avg_price: 0.46, slippage_bps: 5 }],
        sell: [{ size: 50, avg_price: 0.45, slippage_bps: 6 }],
      },
      source: 'snapshot',
    },
    strategy: {
      name: 'high_prob_yes',
      version: '1.0.0',
      enabled: true,
      parameters: [
        { key: 'price_threshold', label: 'Price Threshold', type: 'number', value: 0.95, defaultValue: 0.95, min: 0.5, max: 1.0, step: 0.01 },
        { key: 'position_size', label: 'Position Size', type: 'number', value: 20, defaultValue: 20, min: 1, max: 100, step: 1, unit: '$' },
        { key: 'min_hold_days', label: 'Min Hold Days', type: 'number', value: 7, defaultValue: 7, min: 0, max: 30, step: 1, unit: 'days' },
        { key: 'profit_target', label: 'Profit Target', type: 'number', value: 0.99, defaultValue: 0.99, min: 0.5, max: 1.0, step: 0.01 },
        { key: 'stop_loss', label: 'Stop Loss', type: 'number', value: 0.9, defaultValue: 0.9, min: 0.5, max: 1.0, step: 0.01 },
      ],
      filters: {
        blockedCategories: ['Weather', 'Sports'],
        weatherFilterEnabled: true,
        minTradeSize: 50,
        maxTradeAge: 300,
        minTimeToExpiry: 6,
        maxPriceDeviation: 0.1,
      },
      lastModified: isoNow,
    },
    system: {
      environment: 'development',
      version: '1.0.0',
      commit_hash: 'abc123',
      api_base_url: 'http://localhost:9050',
      ws_base_url: 'wss://ws-subscriptions-clob.polymarket.com',
      features: {
        live_trading: false,
        websocket: true,
        telegram_alerts: false,
      },
      uptime: 86400,
    },
    logs: {
      logs: [
        { id: 'log_1', level: 'info', timestamp: isoNow, message: 'Bot started', source: 'main' },
        { id: 'log_2', level: 'debug', timestamp: isoNow, message: 'WebSocket connected', source: 'ingestion' },
        { id: 'log_3', level: 'error', timestamp: isoNow, message: 'Order rejected', source: 'execution' },
      ],
    },
    decisions: {
      decisions: [
        {
          id: 'sig_1',
          marketId: 'mkt_1',
          tokenId: 'tok_abc123',
          question: 'Will Bitcoin reach $100k by end of 2024?',
          timestamp: isoNow,
          triggerPrice: 0.96,
          tradeSize: 50,
          modelScore: 0.97,
          decision: 'entry',
          reason: 'Model score above threshold',
          filters: {
            g1Passed: true,
            g5Passed: true,
            g6Passed: true,
            sizePassed: true,
          },
        },
      ],
    },
    pipelineFunnel: {
      funnel: [
        { stage: 'threshold', label: 'Below Threshold', count: 500, percentage: 50 },
        { stage: 'g1_trade_age', label: 'Trade Too Old (G1)', count: 200, percentage: 20 },
        { stage: 'g5_orderbook', label: 'Orderbook Divergence (G5)', count: 100, percentage: 10 },
        { stage: 'g6_weather', label: 'Weather Market (G6)', count: 80, percentage: 8 },
        { stage: 'duplicate', label: 'Duplicate Trigger', count: 50, percentage: 5 },
        { stage: 'trade_size', label: 'Trade Size Too Small', count: 28, percentage: 2.8 },
      ],
      total_rejections: 958,
      minutes: 60,
      samples: {},
      near_miss_count: 15,
      candidate_count: 8,
    },
    pipelineRejections: {
      rejections: [
        {
          token_id: 'tok_stale',
          condition_id: 'cond_old',
          stage: 'g1_trade_age',
          timestamp: new Date(now - 600000).toISOString(),
          price: 0.91,
          question: 'Will inflation fall below 2% in 2025?',
          trade_size: 40,
          trade_age_seconds: 540,
          rejection_values: { age_seconds: 540, max_age: 300 },
          outcome: 'YES',
          rejection_reason: 'Trade too old (G1)',
        },
      ],
    },
    pipelineCandidates: {
      candidates: [
        {
          token_id: 'tok_abc123',
          condition_id: 'cond_xyz',
          question: 'Will Bitcoin reach $100k by end of 2024?',
          current_price: 0.96,
          threshold: 0.95,
          distance_to_threshold: -0.01,
          last_updated: isoNow,
          last_signal: 'ENTRY',
          last_signal_reason: 'Model score above threshold',
          model_score: 0.92,
          time_to_end_hours: 120,
          trade_size: 100,
          trade_age_seconds: 120,
          highest_price_seen: 0.97,
          times_evaluated: 12,
          outcome: 'YES',
          is_near_miss: false,
          is_above_threshold: true,
          status_label: 'Triggered (Held)',
        },
      ],
    },
    nearMisses: {
      near_misses: [],
    },
    pipelineStats: {
      totals: {
        threshold: 500,
        duplicate: 50,
        g1_trade_age: 200,
        g5_orderbook: 100,
        g6_weather: 80,
        time_to_end: 0,
        trade_size: 28,
        category: 0,
        manual_block: 0,
        max_positions: 0,
        strategy_hold: 0,
        strategy_ignore: 0,
      },
      total: 958,
      minutes: 60,
    },
  };

  return { ...base, ...overrides };
}

export async function setupApiMocks(page: Page, overrides: Partial<MockData> = {}) {
  const mocks = buildMockData(overrides);

  await page.route('**/api/status', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.status) });
  });
  await page.route('**/api/metrics', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.metrics) });
  });
  await page.route('**/health', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.health) });
  });
  await page.route('**/api/positions/flatten', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/positions/*/close', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/positions', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.positions) });
  });
  await page.route('**/api/orders/cancel_all', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/orders**', (route) => {
    const method = route.request().method();
    const body = method === 'POST' ? { success: true } : mocks.orders;
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.route('**/api/activity**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.activity) });
  });
  await page.route('**/api/risk', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.risk) });
  });
  await page.route('**/api/performance**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.performance) });
  });
  await page.route('**/api/markets**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.markets) });
  });
  await page.route('**/api/market/*/history**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.marketHistory) });
  });
  await page.route('**/api/market/*/orderbook**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.marketOrderbook) });
  });
  await page.route('**/api/market/*/block', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/market/*', (route) => {
    const url = new URL(route.request().url());
    const conditionId = url.pathname.split('/').pop() ?? 'cond_xyz';
    const responseBody = {
      ...mocks.marketDetail,
      market: {
        ...(mocks.marketDetail as { market?: Record<string, unknown> }).market,
        condition_id: conditionId,
      },
    };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseBody) });
  });
  await page.route('**/api/strategy', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.strategy) });
  });
  await page.route('**/api/system', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.system) });
  });
  await page.route('**/api/logs**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.logs) });
  });
  await page.route('**/api/decisions**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.decisions) });
  });
  await page.route('**/api/pipeline/funnel**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.pipelineFunnel) });
  });
  await page.route('**/api/pipeline/rejections**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.pipelineRejections) });
  });
  await page.route('**/api/pipeline/candidates**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.pipelineCandidates) });
  });
  await page.route('**/api/pipeline/near-misses**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.nearMisses) });
  });
  await page.route('**/api/pipeline/stats**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.pipelineStats) });
  });
  await page.route('**/api/control/pause', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/control/resume', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/control/kill', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
  await page.route('**/api/stream', (route) => {
    route.abort();
  });
}
