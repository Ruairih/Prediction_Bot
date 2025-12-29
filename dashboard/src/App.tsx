/**
 * Main Application Component
 *
 * Root component with routing and layout structure.
 */
import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { Sidebar } from './components/common/Sidebar';
import { StatusBar } from './components/common/StatusBar';
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
      <div className="h-screen flex flex-col bg-transparent text-text-primary">
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
        />

        {/* Main Content Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar Navigation */}
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          />

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto">
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
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}

/**
 * Main App component with QueryClientProvider wrapper
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

export default App;
