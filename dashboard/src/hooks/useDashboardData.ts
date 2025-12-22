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
  fetchTriggers,
  fetchHealth,
  fetchDashboardData,
} from '../api/dashboard';

// Query keys for cache management
export const queryKeys = {
  status: ['bot-status'] as const,
  metrics: ['metrics'] as const,
  positions: ['positions'] as const,
  triggers: ['triggers'] as const,
  health: ['health'] as const,
  dashboard: ['dashboard'] as const,
};

/**
 * Hook for bot status
 */
export function useBotStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: fetchBotStatus,
    refetchInterval: 10000,  // Refetch every 10 seconds
    staleTime: 5000,
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
 * Hook for recent triggers/activity
 */
export function useTriggers(limit = 20) {
  return useQuery({
    queryKey: [...queryKeys.triggers, limit],
    queryFn: () => fetchTriggers(limit),
    refetchInterval: 10000,  // Refetch every 10 seconds
    staleTime: 5000,
    retry: 2,
  });
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
 * Combined dashboard data hook - fetches all data in parallel
 */
export function useDashboardData() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: fetchDashboardData,
    refetchInterval: 10000,
    staleTime: 5000,
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
    queryClient.invalidateQueries({ queryKey: queryKeys.triggers });
    queryClient.invalidateQueries({ queryKey: queryKeys.health });
  };
}
