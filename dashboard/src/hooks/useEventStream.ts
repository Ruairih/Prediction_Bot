/**
 * SSE Event Stream Hook
 *
 * Subscribes to /api/stream and invalidates queries on updates.
 */
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from './useDashboardData';

export function useEventStream() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const apiKey = typeof window !== 'undefined' ? window.localStorage.getItem('dashboard_api_key') : null;
    const streamUrl = apiKey ? `/api/stream?api_key=${encodeURIComponent(apiKey)}` : '/api/stream';
    const source = new EventSource(streamUrl);

    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        switch (payload.type) {
          case 'price':
          case 'signal':
            queryClient.invalidateQueries({ queryKey: queryKeys.activity });
            queryClient.invalidateQueries({ queryKey: queryKeys.marketDetail });
            queryClient.invalidateQueries({ queryKey: queryKeys.marketHistory });
            break;
          case 'order':
          case 'fill':
            queryClient.invalidateQueries({ queryKey: queryKeys.orders });
            queryClient.invalidateQueries({ queryKey: queryKeys.metrics });
            queryClient.invalidateQueries({ queryKey: queryKeys.activity });
            break;
          case 'position':
            queryClient.invalidateQueries({ queryKey: queryKeys.positions });
            queryClient.invalidateQueries({ queryKey: queryKeys.performance });
            queryClient.invalidateQueries({ queryKey: queryKeys.metrics });
            queryClient.invalidateQueries({ queryKey: queryKeys.risk });
            queryClient.invalidateQueries({ queryKey: queryKeys.activity });
            break;
          case 'bot_state':
            queryClient.invalidateQueries({ queryKey: queryKeys.status });
            queryClient.invalidateQueries({ queryKey: queryKeys.activity });
            break;
          default:
            queryClient.invalidateQueries({ queryKey: queryKeys.activity });
            break;
        }
      } catch {
        // Ignore malformed SSE payloads
      }
    };

    source.onerror = () => {
      // EventSource will reconnect automatically
    };

    return () => {
      source.close();
    };
  }, [queryClient]);
}
