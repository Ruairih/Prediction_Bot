/**
 * Main Application Component
 *
 * Root component with routing and layout structure.
 * Features a premium multi-theme design system.
 * Implements Error Boundaries to prevent full app crashes.
 */
import { useState } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider } from './contexts/ToastContext';
import { Sidebar } from './components/common/Sidebar';
import { StatusBar } from './components/common/StatusBar';
import { ThemeBackground } from './components/common/ThemeBackground';
import { ErrorBoundary, ErrorFallback, type ErrorFallbackProps } from './components/common/ErrorBoundary';
import { Overview } from './pages/Overview';
import { Positions } from './pages/Positions';
import { Markets } from './pages/Markets';
import { Pipeline } from './pages/Pipeline';
import { Activity } from './pages/Activity';
import { Performance } from './pages/Performance';
import { Strategy } from './pages/Strategy';
import { Risk } from './pages/Risk';
import { System } from './pages/System';
import { Settings } from './pages/Settings';
import { useBotStatus, useMetrics, useHealth } from './hooks/useDashboardData';
import { useEventStream } from './hooks/useEventStream';
import {
  pauseTrading,
  resumeTrading,
  cancelAllOrders,
  flattenPositions,
  killTrading,
} from './api/dashboard';
import type { BotMode } from './types';

/**
 * Custom fallback component for page-level errors
 * Styled to fit within the page content area
 */
function PageErrorFallback(props: ErrorFallbackProps) {
  return (
    <div className="p-6">
      <div className="card p-6">
        <ErrorFallback {...props} />
      </div>
    </div>
  );
}

/**
 * Route wrapper component that provides error boundaries for each page
 * Uses location.pathname as a reset key to automatically clear errors on navigation
 */
function RouteErrorBoundary({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <ErrorBoundary
      resetKey={location.pathname}
      fallback={(props) => <PageErrorFallback {...props} />}
      onError={(error, errorInfo) => {
        // Log to console with additional context
        console.error('[RouteErrorBoundary] Page error on', location.pathname);
        console.error('[RouteErrorBoundary] Error:', error.message);
        console.error('[RouteErrorBoundary] Component stack:', errorInfo.componentStack);
      }}
    >
      {children}
    </ErrorBoundary>
  );
}

/**
 * Top-level fallback for catastrophic errors that occur outside page components
 * (e.g., in providers, layout components, or the StatusBar)
 */
function AppErrorFallback(props: ErrorFallbackProps) {
  return (
    <div className="h-screen flex items-center justify-center bg-bg-primary">
      <div className="max-w-xl w-full mx-4">
        <div className="card p-8">
          <ErrorFallback {...props} />
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-text-muted text-sm text-center">
              If the problem persists, try refreshing the page or clearing your browser cache.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchInterval: 10000,
    },
  },
});

/**
 * Inner app component that can use React Query hooks
 */
function AppContent() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const queryClient = useQueryClient();
  useEventStream();

  // Fetch real data from API
  const { data: statusData, error: statusError } = useBotStatus();
  const { data: metricsData } = useMetrics();
  const { data: healthData } = useHealth();

  // Derive values from API data with fallbacks
  const mode: BotMode = statusData?.mode ?? 'stopped';
  const balance = metricsData?.availableBalance ?? 0;
  const lastHeartbeat = statusData?.lastHeartbeat ?? null;
  const isConnected = !statusError && statusData?.status !== 'unhealthy';
  const healthStatus = healthData?.overall;
  const dbLatencyMs = healthData?.database.latencyMs ?? null;
  const wsConnected = healthData?.websocket.connected ?? null;

  const handleKillSwitch = async () => {
    if (!window.confirm('Trigger kill switch? This will stop the bot.')) {
      return;
    }
    await killTrading('operator_kill');
    queryClient.invalidateQueries();
  };
  const handlePause = async () => {
    await pauseTrading('operator_pause');
    queryClient.invalidateQueries();
  };
  const handleResume = async () => {
    await resumeTrading();
    queryClient.invalidateQueries();
  };
  const handleCancelAll = async () => {
    if (!window.confirm('Cancel all open orders?')) {
      return;
    }
    await cancelAllOrders();
    queryClient.invalidateQueries();
  };
  const handleCloseAll = async () => {
    if (!window.confirm('Flatten all open positions?')) {
      return;
    }
    await flattenPositions('operator_flatten');
    queryClient.invalidateQueries();
  };

  return (
    <BrowserRouter>
      {/* Artistic theme background */}
      <ThemeBackground />

      <div className="h-screen flex flex-col bg-transparent text-text-primary relative" style={{ zIndex: 1 }}>
        {/* Top Status Bar */}
        <StatusBar
          mode={mode}
          balance={balance}
          isConnected={isConnected}
          lastHeartbeat={lastHeartbeat}
          healthStatus={healthStatus}
          dbLatencyMs={dbLatencyMs}
          wsConnected={wsConnected}
          onPause={handlePause}
          onResume={handleResume}
          onCancelAll={handleCancelAll}
          onCloseAll={handleCloseAll}
          onKillSwitch={handleKillSwitch}
          onMobileMenuToggle={() => setMobileSidebarOpen(!mobileSidebarOpen)}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar Navigation */}
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
            mobileOpen={mobileSidebarOpen}
            onMobileClose={() => setMobileSidebarOpen(false)}
          />

          {/* Page Content - Wrapped in RouteErrorBoundary for page-level error isolation */}
          <main className="flex-1 overflow-y-auto">
            <RouteErrorBoundary>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/positions" element={<Positions />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/pipeline" element={<Pipeline />} />
                <Route path="/strategy" element={<Strategy />} />
                <Route path="/performance" element={<Performance />} />
                <Route path="/risk" element={<Risk />} />
                <Route path="/activity" element={<Activity />} />
                <Route path="/system" element={<System />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </RouteErrorBoundary>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}

/**
 * Main App component with QueryClientProvider, ThemeProvider, and Error Boundary wrappers
 *
 * Error Boundary hierarchy:
 * 1. Top-level ErrorBoundary - catches catastrophic errors in providers/layout
 * 2. RouteErrorBoundary - catches page-level errors, keeps StatusBar/Sidebar accessible
 */
function App() {
  return (
    <ErrorBoundary
      fallback={(props) => <AppErrorFallback {...props} />}
      onError={(error, errorInfo) => {
        console.error('[AppErrorBoundary] Catastrophic error caught');
        console.error('[AppErrorBoundary] Error:', error.message);
        console.error('[AppErrorBoundary] Stack:', error.stack);
        console.error('[AppErrorBoundary] Component stack:', errorInfo.componentStack);
      }}
    >
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ToastProvider>
            <AppContent />
          </ToastProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
