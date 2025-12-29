/**
 * Dashboard Data Hooks
 *
 * React Query hooks for fetching dashboard data with caching and refetching.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchBotStatus,
  fetchMetrics,
  fetchPositions,
  fetchOrders,
  fetchRisk,
  fetchActivity,
  fetchHealth,
  fetchDashboardData,
  fetchMarkets,
  fetchPerformance,
  fetchSystemConfig,
  fetchLogs,
  fetchStrategy,
  fetchDecisions,
  fetchMarketDetail,
  fetchMarketHistory,
  fetchMarketOrderbook,
  fetchPipelineFunnel,
  fetchPipelineRejections,
  fetchPipelineCandidates,
  fetchNearMisses,
} from '../api/dashboard';
import type { RejectionStage } from '../types';

// Query keys for cache management
export const queryKeys = {
  status: ['bot-status'] as const,
  metrics: ['metrics'] as const,
  positions: ['positions'] as const,
  orders: ['orders'] as const,
  risk: ['risk'] as const,
  activity: ['activity'] as const,
  health: ['health'] as const,
  dashboard: ['dashboard'] as const,
  markets: ['markets'] as const,
  performance: ['performance'] as const,
  system: ['system'] as const,
  logs: ['logs'] as const,
  strategy: ['strategy'] as const,
  decisions: ['decisions'] as const,
  marketDetail: ['market-detail'] as const,
  marketHistory: ['market-history'] as const,
  marketOrderbook: ['market-orderbook'] as const,
  pipelineFunnel: ['pipeline-funnel'] as const,
  pipelineRejections: ['pipeline-rejections'] as const,
  pipelineCandidates: ['pipeline-candidates'] as const,
  nearMisses: ['near-misses'] as const,
};

/**
 * Hook for bot status
 */
export function useBotStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: fetchBotStatus,
    refetchInterval: 30000,  // Refetch every 30 seconds (was 10s)
    staleTime: 15000,
    retry: 2,
  });
}

/**
 * Hook for trading metrics
 */
export function useMetrics() {
  return useQuery({
    queryKey: queryKeys.metrics,
    queryFn: fetchMetrics,
    refetchInterval: 30000,  // Refetch every 30 seconds
    staleTime: 10000,
    retry: 2,
  });
}

/**
 * Hook for positions
 */
export function usePositions() {
  return useQuery({
    queryKey: queryKeys.positions,
    queryFn: fetchPositions,
    refetchInterval: 15000,  // Refetch every 15 seconds
    staleTime: 5000,
    retry: 2,
  });
}

/**
 * Hook for orders
 */
export function useOrders(limit = 200) {
  return useQuery({
    queryKey: [...queryKeys.orders, limit],
    queryFn: () => fetchOrders(limit),
    refetchInterval: 15000,
    staleTime: 5000,
    retry: 2,
  });
}

/**
 * Hook for risk limits
 */
export function useRisk() {
  return useQuery({
    queryKey: queryKeys.risk,
    queryFn: fetchRisk,
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for markets
 */
export function useMarkets(params?: { limit?: number; q?: string; category?: string }) {
  return useQuery({
    queryKey: [...queryKeys.markets, params],
    queryFn: () => fetchMarkets(params),
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for recent activity
 */
export function useActivity(limit = 20) {
  return useQuery({
    queryKey: [...queryKeys.activity, limit],
    queryFn: () => fetchActivity(limit),
    refetchInterval: 30000,  // Refetch every 30 seconds (was 10s)
    staleTime: 15000,
    retry: 2,
  });
}

/**
 * Backwards-compatible alias for activity.
 */
export function useTriggers(limit = 20) {
  return useActivity(limit);
}

/**
 * Hook for system health
 */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for performance data
 */
export function usePerformance(rangeDays?: number, limit = 200) {
  return useQuery({
    queryKey: [...queryKeys.performance, rangeDays, limit],
    queryFn: () => fetchPerformance(rangeDays, limit),
    refetchInterval: 60000,
    staleTime: 15000,
    retry: 1,
  });
}

/**
 * Hook for system config
 */
export function useSystemConfig() {
  return useQuery({
    queryKey: queryKeys.system,
    queryFn: fetchSystemConfig,
    refetchInterval: 60000,
    staleTime: 30000,
    retry: 1,
  });
}

/**
 * Hook for log entries
 */
export function useLogs(limit = 200) {
  return useQuery({
    queryKey: [...queryKeys.logs, limit],
    queryFn: () => fetchLogs(limit),
    refetchInterval: 15000,
    staleTime: 5000,
    retry: 1,
  });
}

/**
 * Hook for strategy config
 */
export function useStrategy() {
  return useQuery({
    queryKey: queryKeys.strategy,
    queryFn: fetchStrategy,
    refetchInterval: 30000,
    staleTime: 15000,
    retry: 1,
  });
}

/**
 * Hook for decision log
 */
export function useDecisions(limit = 100) {
  return useQuery({
    queryKey: [...queryKeys.decisions, limit],
    queryFn: () => fetchDecisions(limit),
    refetchInterval: 20000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for market detail
 */
export function useMarketDetail(conditionId?: string) {
  return useQuery({
    queryKey: [...queryKeys.marketDetail, conditionId],
    queryFn: () => conditionId ? fetchMarketDetail(conditionId) : Promise.resolve(null),
    enabled: Boolean(conditionId),
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for market history
 */
export function useMarketHistory(conditionId?: string, limit = 200) {
  return useQuery({
    queryKey: [...queryKeys.marketHistory, conditionId, limit],
    queryFn: () => conditionId ? fetchMarketHistory(conditionId, limit) : Promise.resolve([]),
    enabled: Boolean(conditionId),
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Hook for market orderbook
 */
export function useMarketOrderbook(conditionId?: string, tokenId?: string) {
  return useQuery({
    queryKey: [...queryKeys.marketOrderbook, conditionId, tokenId],
    queryFn: () => conditionId ? fetchMarketOrderbook(conditionId, tokenId) : Promise.resolve(null),
    enabled: Boolean(conditionId),
    refetchInterval: 30000,
    staleTime: 10000,
    retry: 1,
  });
}

/**
 * Combined dashboard data hook - fetches all data in parallel
 */
export function useDashboardData() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: fetchDashboardData,
    refetchInterval: 30000,  // Refetch every 30 seconds (was 10s)
    staleTime: 15000,
    retry: 2,
  });
}

/**
 * Hook to manually refresh all dashboard data
 */
export function useRefreshDashboard() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.status });
    queryClient.invalidateQueries({ queryKey: queryKeys.metrics });
    queryClient.invalidateQueries({ queryKey: queryKeys.positions });
    queryClient.invalidateQueries({ queryKey: queryKeys.orders });
    queryClient.invalidateQueries({ queryKey: queryKeys.risk });
    queryClient.invalidateQueries({ queryKey: queryKeys.activity });
    queryClient.invalidateQueries({ queryKey: queryKeys.health });
    queryClient.invalidateQueries({ queryKey: queryKeys.markets });
    queryClient.invalidateQueries({ queryKey: queryKeys.performance });
    queryClient.invalidateQueries({ queryKey: queryKeys.system });
    queryClient.invalidateQueries({ queryKey: queryKeys.logs });
    queryClient.invalidateQueries({ queryKey: queryKeys.strategy });
    queryClient.invalidateQueries({ queryKey: queryKeys.decisions });
    queryClient.invalidateQueries({ queryKey: queryKeys.pipelineFunnel });
    queryClient.invalidateQueries({ queryKey: queryKeys.pipelineRejections });
    queryClient.invalidateQueries({ queryKey: queryKeys.pipelineCandidates });
    queryClient.invalidateQueries({ queryKey: queryKeys.nearMisses });
  };
}

// =============================================================================
// Pipeline Visibility Hooks
// =============================================================================

/**
 * Hook for pipeline funnel summary
 */
export function usePipelineFunnel(minutes = 60) {
  return useQuery({
    queryKey: [...queryKeys.pipelineFunnel, minutes],
    queryFn: () => fetchPipelineFunnel(minutes),
    refetchInterval: 60000,  // Refetch every 60 seconds (was 10s - too aggressive)
    staleTime: 30000,
    retry: 1,
  });
}

/**
 * Hook for pipeline rejections
 */
export function usePipelineRejections(limit = 100, stage?: RejectionStage) {
  return useQuery({
    queryKey: [...queryKeys.pipelineRejections, limit, stage],
    queryFn: () => fetchPipelineRejections(limit, stage),
    refetchInterval: 60000,  // Refetch every 60 seconds (was 15s)
    staleTime: 30000,
    retry: 1,
  });
}

/**
 * Hook for pipeline candidates
 */
export function usePipelineCandidates(limit = 50, sortBy: 'distance' | 'score' | 'recent' = 'distance') {
  return useQuery({
    queryKey: [...queryKeys.pipelineCandidates, limit, sortBy],
    queryFn: () => fetchPipelineCandidates(limit, sortBy),
    refetchInterval: 60000,  // Refetch every 60 seconds (was 15s)
    staleTime: 30000,
    retry: 1,
  });
}

/**
 * Hook for near-miss markets
 */
export function useNearMisses(maxDistance = 0.02) {
  return useQuery({
    queryKey: [...queryKeys.nearMisses, maxDistance],
    queryFn: () => fetchNearMisses(maxDistance),
    refetchInterval: 60000,  // Refetch every 60 seconds (was 15s)
    staleTime: 30000,
    retry: 1,
  });
}
