/**
 * Main Application Component
 *
 * Root component with routing and layout structure.
 */
import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/common/Sidebar';
import { StatusBar } from './components/common/StatusBar';
import { Overview } from './pages/Overview';
import { Positions } from './pages/Positions';
import { Activity } from './pages/Activity';
import { Performance } from './pages/Performance';
import { Strategy } from './pages/Strategy';
import { Risk } from './pages/Risk';
import { System } from './pages/System';
import { useBotStatus, useMetrics } from './hooks/useDashboardData';
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

  // Fetch real data from API
  const { data: statusData, error: statusError } = useBotStatus();
  const { data: metricsData } = useMetrics();

  // Derive values from API data with fallbacks
  const mode: BotMode = statusData?.mode ?? 'stopped';
  const balance = metricsData?.availableBalance ?? 0;
  const isConnected = !statusError && statusData?.status !== 'unhealthy';

  const handleKillSwitch = () => {
    console.log('Kill switch activated');
    // TODO: Implement kill switch API call
  };

  return (
    <BrowserRouter>
      <div className="h-screen flex flex-col bg-bg-primary text-text-primary">
        {/* Top Status Bar */}
        <StatusBar
          mode={mode}
          balance={balance}
          isConnected={isConnected}
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
              <Route path="/strategy" element={<Strategy />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/risk" element={<Risk />} />
              <Route path="/activity" element={<Activity />} />
              <Route path="/system" element={<System />} />
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
