/**
 * React Query hooks for market data
 */

import { useQuery } from '@tanstack/react-query'
import { listMarkets, getMarket, getCategories, getVolumeLeaders, searchMarkets, getCategoriesDetailed, getEventMarkets } from '../api/client'
import type { MarketFilter, SortConfig } from '../types/market'

export function useMarkets(
  filter?: MarketFilter,
  sort?: SortConfig,
  page = 1,
  pageSize = 50
) {
  return useQuery({
    queryKey: ['markets', filter, sort, page, pageSize],
    queryFn: ({ signal }) => listMarkets({ filter, sort, page, pageSize, signal }),
  })
}

export function useMarket(conditionId: string) {
  return useQuery({
    queryKey: ['market', conditionId],
    queryFn: ({ signal }) => getMarket(conditionId, signal),
    enabled: !!conditionId,
  })
}

export function useCategories(resolved?: boolean) {
  return useQuery({
    queryKey: ['categories', resolved],
    queryFn: ({ signal }) => getCategories(resolved, signal),
    staleTime: 60_000, // Categories change slowly
  })
}

export function useVolumeLeaders(category?: string, limit = 10) {
  return useQuery({
    queryKey: ['volume-leaders', category, limit],
    queryFn: ({ signal }) => getVolumeLeaders(category, limit, signal),
  })
}

export function useSearchMarkets(query: string, limit = 20) {
  return useQuery({
    queryKey: ['search', query, limit],
    queryFn: ({ signal }) => searchMarkets(query, limit, signal),
    enabled: query.length >= 2,
  })
}

export function useCategoriesDetailed(
  page = 1,
  pageSize = 50,
  search?: string,
  minMarkets = 1
) {
  return useQuery({
    queryKey: ['categories-detailed', page, pageSize, search, minMarkets],
    queryFn: ({ signal }) => getCategoriesDetailed({
      page,
      pageSize,
      search,
      minMarkets,
      signal,
    }),
    staleTime: 60_000, // Categories change slowly
  })
}

export function useEventMarkets(eventId: string | null) {
  return useQuery({
    queryKey: ['event-markets', eventId],
    queryFn: ({ signal }) => getEventMarkets(eventId!, signal),
    enabled: !!eventId,
  })
}
