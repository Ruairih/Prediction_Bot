# Polymarket Trading Dashboard

## What This Is

A **React/TypeScript trading dashboard** for monitoring and controlling a Polymarket prediction market trading bot. This dashboard runs independently on port 3000 and communicates with a Flask backend API on port 9050.

**Key principle:** This is a standalone frontend application. You do NOT need to understand the trading bot's Python backend to work on this dashboard effectively.

---

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (port 3000)
npm run dev

# Run unit tests
npm test

# Run E2E tests (requires bot backend running)
npm run test:e2e

# Build for production
npm run build

# Lint code
npm run lint
```

**Requirements:**
- Node.js 18+
- Backend API running on port 9050 (for live data)

---

## Tech Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| **React** | UI framework | ^18.2.0 |
| **TypeScript** | Type safety | ^5.2.2 |
| **Vite** | Build tool & dev server | ^5.0.0 |
| **TanStack Query** | Server state management | ^5.8.0 |
| **React Router** | Client-side routing | ^6.20.0 |
| **Tailwind CSS** | Utility-first styling | ^3.3.5 |
| **Recharts** | Data visualization | ^2.10.0 |
| **Vitest** | Unit testing | ^1.0.0 |
| **Playwright** | E2E testing | ^1.40.0 |
| **clsx** | Conditional classnames | ^2.0.0 |
| **date-fns** | Date formatting | ^2.30.0 |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Application                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Contexts   │    │    Hooks     │    │     API      │       │
│  │              │    │              │    │              │       │
│  │ ThemeContext │───▶│ useDashboard │───▶│ dashboard.ts │       │
│  │              │    │ useEventStrm │    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                      Components                       │       │
│  │                                                       │       │
│  │  common/     overview/    positions/   performance/  │       │
│  │  activity/   risk/        strategy/    system/       │       │
│  └──────────────────────────────────────────────────────┘       │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                        Pages                          │       │
│  │  Overview | Positions | Markets | Pipeline | ...     │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/SSE
                              ▼
                    ┌──────────────────┐
                    │  Flask Backend   │
                    │   (port 9050)    │
                    └──────────────────┘
```

### Data Flow

1. **React Query** fetches data from Flask API via `src/api/dashboard.ts`
2. **SSE stream** (`useEventStream`) pushes real-time updates
3. **Components** consume data via custom hooks in `src/hooks/`
4. **Theme system** applies dynamic CSS variables via `ThemeContext`

---

## File Structure

```
dashboard/
├── CLAUDE.md                 ← You are here
├── package.json              ← Dependencies & scripts
├── vite.config.ts            ← Vite + proxy configuration
├── tailwind.config.js        ← Tailwind + theme CSS vars
├── tsconfig.json             ← TypeScript configuration
├── index.html                ← Entry HTML
├── e2e/                      ← Playwright E2E tests
│   └── *.spec.ts
└── src/
    ├── main.tsx              ← React entry point
    ├── App.tsx               ← Root component with routing
    ├── index.css             ← Global styles + CSS variables
    ├── types/
    │   └── index.ts          ← All TypeScript interfaces
    ├── api/
    │   └── dashboard.ts      ← API client (snake_case → camelCase)
    ├── hooks/
    │   ├── useDashboardData.ts  ← React Query hooks
    │   └── useEventStream.ts    ← SSE subscription
    ├── contexts/
    │   └── ThemeContext.tsx  ← 5 theme system
    ├── pages/                ← Route-level components
    │   ├── Overview.tsx      ← Main dashboard (/)
    │   ├── Positions.tsx     ← Portfolio (/positions)
    │   ├── Markets.tsx       ← Market explorer (/markets)
    │   ├── Pipeline.tsx      ← Signal funnel (/pipeline)
    │   ├── Strategy.tsx      ← Trading rules (/strategy)
    │   ├── Performance.tsx   ← P&L analytics (/performance)
    │   ├── Risk.tsx          ← Exposure limits (/risk)
    │   ├── Activity.tsx      ← Event stream (/activity)
    │   ├── System.tsx        ← Health status (/system)
    │   └── Settings.tsx      ← Preferences (/settings)
    ├── components/
    │   ├── common/           ← Shared UI components
    │   │   ├── Sidebar.tsx
    │   │   ├── StatusBar.tsx
    │   │   ├── ThemeBackground.tsx
    │   │   ├── EmptyState.tsx
    │   │   ├── Pagination.tsx
    │   │   └── PnlBadge.tsx
    │   ├── overview/         ← Overview page components
    │   ├── positions/        ← Positions page components
    │   ├── activity/         ← Activity page components
    │   └── performance/      ← Performance page components
    └── test/
        └── setup.ts          ← Vitest setup
```

---

## Routing

| Path | Page | Description |
|------|------|-------------|
| `/` | Overview | Main dashboard with KPIs and activity |
| `/positions` | Positions | Open positions table with P&L |
| `/markets` | Markets | Market explorer with search |
| `/pipeline` | Pipeline | Signal funnel visualization |
| `/strategy` | Strategy | Trading rules configuration |
| `/performance` | Performance | P&L charts and trade history |
| `/risk` | Risk | Exposure limits and alerts |
| `/activity` | Activity | Real-time event stream |
| `/system` | System | Service health status |
| `/settings` | Settings | Theme selection & preferences |

---

## Theme System

The dashboard features **5 selectable themes** managed by `ThemeContext`:

| Theme | Description | Vibe |
|-------|-------------|------|
| `midnight-pro` | Bloomberg Terminal inspired | Professional dark |
| `aurora` | Northern lights gradients | Ethereal dark |
| `cyber` | Neon cyberpunk | Futuristic |
| `obsidian` | Black with gold accents | Luxury dark |
| `daylight` | Clean warm light | Light mode |

### How Theming Works

1. `ThemeContext.tsx` defines all themes with color tokens
2. On theme change, CSS custom properties are set on `:root`
3. `tailwind.config.js` maps these CSS vars to Tailwind classes
4. `index.css` provides additional utility classes

### Using Theme Colors

```tsx
// Tailwind classes (preferred)
<div className="bg-bg-primary text-text-primary border-border" />
<span className="text-positive" />  // Green for profits
<span className="text-negative" />  // Red for losses
<span className="text-accent-primary" />  // Theme accent

// Direct CSS variables (when needed)
style={{ color: 'var(--accent-primary)' }}
```

### Key CSS Custom Properties

```css
--bg-primary      /* Main background */
--bg-secondary    /* Card backgrounds */
--bg-tertiary     /* Elevated surfaces */
--bg-glass        /* Glass morphism */
--text-primary    /* Main text */
--text-secondary  /* Secondary text */
--text-muted      /* Muted/disabled text */
--border          /* Standard borders */
--accent-primary  /* Theme accent color */
--positive        /* Success/profit (green) */
--negative        /* Error/loss (red) */
--warning         /* Warning (yellow) */
```

---

## API Integration

### Client: `src/api/dashboard.ts`

The API client handles:
- All HTTP requests to the Flask backend
- snake_case → camelCase transformation
- API key authentication (stored in localStorage)

### Key Functions

```typescript
// Status & Health
fetchBotStatus()      // Bot mode, health, version
fetchHealth()         // Service statuses, latencies
fetchMetrics()        // P&L, win rate, positions count

// Trading Data
fetchPositions()      // Open positions
fetchOrders(limit)    // Order history
fetchMarkets(params)  // Market list with search

// Performance
fetchPerformance(rangeDays, limit)  // Stats, equity curve, trades

// Pipeline
fetchPipelineFunnel(minutes)   // Signal rejection funnel
fetchPipelineCandidates(limit) // Near-threshold markets
fetchNearMisses(maxDistance)   // Markets that almost triggered

// Control Actions
pauseTrading(reason)
resumeTrading()
killTrading(reason)
cancelAllOrders()
flattenPositions(reason)
closePosition(positionId, price, reason)
blockMarket(conditionId, reason)
```

### Backend Proxy

Vite proxies `/api/*` and `/health` to `localhost:9050`:

```typescript
// vite.config.ts
proxy: {
  '/api': { target: 'http://localhost:9050', changeOrigin: true },
  '/health': { target: 'http://localhost:9050', changeOrigin: true },
}
```

---

## React Query Hooks

All data fetching uses TanStack Query via `src/hooks/useDashboardData.ts`:

```typescript
// Core data hooks
useBotStatus()        // Bot status (30s refetch)
useMetrics()          // Trading metrics (30s refetch)
usePositions()        // Open positions (15s refetch)
useOrders(limit)      // Order history (15s refetch)
useRisk()             // Risk limits (30s refetch)
useActivity(limit)    // Activity events (30s refetch)
useHealth()           // System health (30s refetch)

// Markets & Performance
useMarkets(params)    // Market list
usePerformance(rangeDays, limit)  // P&L data

// Pipeline visibility
usePipelineFunnel(minutes)
usePipelineRejections(limit, stage)
usePipelineCandidates(limit, sortBy)
useNearMisses(maxDistance)

// Market detail
useMarketDetail(conditionId)
useMarketHistory(conditionId, limit)
useMarketOrderbook(conditionId, tokenId)
```

### Query Key Pattern

```typescript
export const queryKeys = {
  status: ['bot-status'],
  metrics: ['metrics'],
  positions: ['positions'],
  orders: ['orders'],
  // ... etc
};
```

### Manual Refresh

```typescript
const refresh = useRefreshDashboard();
refresh(); // Invalidates all queries
```

---

## Real-Time Updates (SSE)

`useEventStream()` subscribes to `/api/stream` for push updates:

```typescript
// Automatically invalidates relevant queries on events:
// 'price', 'signal' → activity, marketDetail
// 'order', 'fill' → orders, metrics, activity
// 'position' → positions, performance, metrics, risk
// 'bot_state' → status, activity
```

---

## Component Patterns

### Page Component Pattern

```tsx
export function PageName() {
  // 1. Fetch data with hooks
  const { data, isLoading, error } = usePageData();

  // 2. Handle loading state
  if (isLoading) return <LoadingSkeleton />;
  if (error) return <ErrorState />;

  // 3. Render content
  return (
    <div className="p-6 space-y-6">
      <header className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold text-text-primary">Title</h1>
      </header>
      {/* Content */}
    </div>
  );
}
```

### Card Component Pattern

```tsx
<div className="card p-6">
  <h2 className="text-label text-text-muted mb-4">SECTION TITLE</h2>
  {/* Content */}
</div>

// Or with hover effect:
<div className="card card-hover p-6">
```

### KPI Tile Pattern

```tsx
<div className="kpi-tile">
  <div className="kpi-label">METRIC NAME</div>
  <div className="kpi-value text-text-primary">$1,234.56</div>
  <div className="kpi-change text-positive">+12.3%</div>
</div>
```

### P&L Coloring

```tsx
import clsx from 'clsx';

<span className={clsx(
  pnl >= 0 ? 'text-positive' : 'text-negative'
)}>
  {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
</span>
```

---

## Styling Guide

### Use Tailwind Theme Classes

```tsx
// Backgrounds
bg-bg-primary    // Main background
bg-bg-secondary  // Card background
bg-bg-tertiary   // Elevated/hover background
bg-bg-glass      // Glass morphism

// Text
text-text-primary    // Main text
text-text-secondary  // Secondary text
text-text-muted      // Muted text

// Borders
border-border        // Standard border
border-border-subtle // Subtle border

// Semantic colors
text-positive / bg-positive  // Success/profit
text-negative / bg-negative  // Error/loss
text-warning / bg-warning    // Warning
text-accent-primary          // Theme accent
```

### Glass Morphism

```tsx
<div className="glass-card p-6">
  {/* Blurred glass background */}
</div>
```

### Data Tables

```tsx
<table className="data-table">
  <thead>
    <tr><th>Column</th></tr>
  </thead>
  <tbody>
    <tr><td>Value</td></tr>
  </tbody>
</table>
```

### Buttons

```tsx
<button className="btn btn-primary">Primary</button>
<button className="btn btn-secondary">Secondary</button>
<button className="btn btn-ghost">Ghost</button>
<button className="btn btn-danger">Danger</button>
```

---

## TypeScript Types

All types are defined in `src/types/index.ts`. Key types:

```typescript
// Bot State
type BotMode = 'live' | 'dry_run' | 'paused' | 'stopped';
type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

// Trading
interface Position { positionId, tokenId, size, entryPrice, currentPrice, unrealizedPnl, ... }
interface Order { orderId, tokenId, side, price, size, status, ... }
type OrderSide = 'BUY' | 'SELL';
type OrderStatus = 'pending' | 'live' | 'partial' | 'filled' | 'cancelled' | 'failed';

// Markets
interface MarketSummary { marketId, conditionId, question, bestBid, bestAsk, ... }
interface MarketDetailResponse { market, position, orders, tokens, lastSignal, lastFill, lastTrade }

// Performance
interface PerformanceStats { totalPnl, winRate, sharpeRatio, maxDrawdown, ... }
interface Trade { tradeId, question, side, entryPrice, exitPrice, pnl, ... }

// Pipeline
type RejectionStage = 'threshold' | 'duplicate' | 'g1_trade_age' | 'g5_orderbook' | ...;
interface CandidateMarket { tokenId, question, currentPrice, threshold, distanceToThreshold, ... }
```

---

## Testing

### Unit Tests (Vitest)

```bash
npm test          # Run all tests
npm run test:ui   # Open Vitest UI
```

Tests are colocated with components:
- `src/components/overview/BotStatus.test.tsx`
- `src/components/overview/KpiTile.test.tsx`

### E2E Tests (Playwright)

```bash
npm run test:e2e       # Run E2E tests
npm run test:e2e:ui    # Open Playwright UI
```

Tests are in `e2e/` directory:
- `e2e/overview.spec.ts`

### Test Setup

```typescript
// src/test/setup.ts
import '@testing-library/jest-dom';
```

---

## Conventions & Best Practices

### DO

- Use `clsx()` for conditional classnames
- Use theme CSS variables via Tailwind classes
- Format currency with `toLocaleString('en-US', { style: 'currency', currency: 'USD' })`
- Format percentages with `toFixed(2)%`
- Use tabular-nums for numeric displays: `className="tabular-nums"`
- Add `data-testid` attributes for E2E tests
- Export component interfaces for reusability

### DON'T

- Don't hardcode colors - always use theme variables
- Don't use inline styles unless necessary for dynamic values
- Don't make API calls directly - use the hooks
- Don't store component state that should be server state
- Don't forget loading and error states

### File Naming

- Components: `PascalCase.tsx`
- Hooks: `useCamelCase.ts`
- Tests: `*.test.tsx` (colocated) or `e2e/*.spec.ts`
- Types: Exported from `types/index.ts`

---

## Common Tasks

### Add a New Page

1. Create `src/pages/NewPage.tsx`
2. Add route in `src/App.tsx`:
   ```tsx
   <Route path="/new-page" element={<NewPage />} />
   ```
3. Add nav item in `src/components/common/Sidebar.tsx`:
   ```tsx
   { path: '/new-page', label: 'New Page', icon: '◉', description: 'Description' }
   ```

### Add a New API Endpoint

1. Add fetch function in `src/api/dashboard.ts`:
   ```typescript
   export async function fetchNewData(): Promise<NewDataType> {
     const response = await apiFetch(`${API_BASE}/api/new-endpoint`);
     // Transform snake_case to camelCase
     return { ... };
   }
   ```

2. Add hook in `src/hooks/useDashboardData.ts`:
   ```typescript
   export function useNewData() {
     return useQuery({
       queryKey: ['new-data'],
       queryFn: fetchNewData,
       refetchInterval: 30000,
     });
   }
   ```

### Add a New Theme

1. Add theme definition in `src/contexts/ThemeContext.tsx`:
   ```typescript
   'new-theme': {
     name: 'new-theme',
     label: 'New Theme',
     description: 'Description',
     isDark: true,
     colors: { ... },
     effects: { ... },
   }
   ```

2. Add to `ThemeName` type:
   ```typescript
   export type ThemeName = 'midnight-pro' | ... | 'new-theme';
   ```

### Add a New Component

1. Create component file: `src/components/{section}/NewComponent.tsx`
2. Export from index: `src/components/{section}/index.ts`
3. Add test: `src/components/{section}/NewComponent.test.tsx`

---

## Gotchas & Known Issues

### D1: API Response Case Transformation

The Flask backend returns snake_case, but the frontend uses camelCase. All transformations happen in `src/api/dashboard.ts`. If you see a snake_case property in the UI, the transformation is missing.

### D2: SSE Reconnection

`EventSource` auto-reconnects on disconnect. The `useEventStream` hook handles this gracefully. Don't add manual reconnection logic.

### D3: Query Invalidation on Actions

After control actions (pause, resume, etc.), you must invalidate queries:
```typescript
await pauseTrading('reason');
queryClient.invalidateQueries();
```

### D4: Theme Flash on Load

The default theme is set before hydration. If localStorage has a different theme, there may be a brief flash. This is expected behavior.

### D5: Proxy Only in Dev Mode

The Vite proxy only works in development. Production builds must be served behind a reverse proxy that routes `/api` to the backend.

### D6: Large Table Performance

For tables with 100+ rows (e.g., Orders, Activity), consider virtual scrolling. Currently uses simple pagination.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_HOST` | `0.0.0.0` | Dev server bind address |

The backend URL is hardcoded to `localhost:9050` via Vite proxy. For production, configure your reverse proxy.

---

## Debugging

### React Query DevTools

Add to `App.tsx` for debugging:
```tsx
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

// Inside QueryClientProvider:
<ReactQueryDevtools initialIsOpen={false} />
```

### Check API Responses

Open browser DevTools → Network tab → Filter by `api` to see all requests/responses.

### Theme Debugging

Check CSS variables in DevTools → Elements → `:root` to see applied theme values.

---

## Backend API Reference

The dashboard expects these endpoints on `localhost:9050`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health check |
| `/api/status` | GET | Bot status |
| `/api/metrics` | GET | Trading metrics |
| `/api/positions` | GET | Open positions |
| `/api/orders` | GET | Order history |
| `/api/markets` | GET | Market list |
| `/api/activity` | GET | Activity events |
| `/api/risk` | GET/POST | Risk limits |
| `/api/performance` | GET | P&L data |
| `/api/strategy` | GET | Strategy config |
| `/api/system` | GET | System config |
| `/api/logs` | GET | Log entries |
| `/api/pipeline/*` | GET | Pipeline data |
| `/api/market/:id` | GET | Market detail |
| `/api/market/:id/orderbook` | GET | Orderbook |
| `/api/market/:id/history` | GET | Trade history |
| `/api/control/pause` | POST | Pause trading |
| `/api/control/resume` | POST | Resume trading |
| `/api/control/kill` | POST | Kill switch |
| `/api/orders/cancel_all` | POST | Cancel all orders |
| `/api/positions/flatten` | POST | Close all positions |
| `/api/stream` | SSE | Real-time events |

---

## Performance Considerations

- **Query Stale Time**: Most queries have 10-30s stale time to avoid over-fetching
- **Refetch Intervals**: Range from 15s (positions) to 60s (performance)
- **SSE**: Triggers targeted invalidation, not full refresh
- **Bundle Size**: Use dynamic imports for heavy pages if needed

---

## Related Documentation

This dashboard is part of the Polymarket Trading Bot. For backend context:
- Backend API: `src/polymarket_bot/monitoring/dashboard.py`
- The root `CLAUDE.md` has full system architecture

However, you should NOT need to read the backend code for most dashboard tasks.
