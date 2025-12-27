/**
 * API Client for Market Explorer Backend
 */

import type { Market, PaginatedMarkets, CategoryCounts, MarketFilter, SortConfig } from '../types/market'

const API_BASE = '/api'

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal })
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export interface ListMarketsParams {
  filter?: MarketFilter
  sort?: SortConfig
  page?: number
  pageSize?: number
  signal?: AbortSignal
}

export async function listMarkets(params: ListMarketsParams = {}): Promise<PaginatedMarkets> {
  const { filter, sort, page = 1, pageSize = 50, signal } = params

  const searchParams = new URLSearchParams()
  searchParams.set('page', page.toString())
  searchParams.set('page_size', pageSize.toString())

  if (filter?.categories?.length) {
    searchParams.set('categories', filter.categories.join(','))
  }
  if (filter?.status?.length) {
    searchParams.set('status', filter.status.join(','))
  }
  if (filter?.min_price !== undefined) {
    searchParams.set('min_price', filter.min_price.toString())
  }
  if (filter?.max_price !== undefined) {
    searchParams.set('max_price', filter.max_price.toString())
  }
  if (filter?.min_volume_24h !== undefined) {
    searchParams.set('min_volume_24h', filter.min_volume_24h.toString())
  }
  if (filter?.min_liquidity_score !== undefined) {
    searchParams.set('min_liquidity_score', filter.min_liquidity_score.toString())
  }
  if (filter?.search) {
    searchParams.set('search', filter.search)
  }
  if (filter?.resolved !== undefined) {
    searchParams.set('resolved', filter.resolved.toString())
  }

  if (sort) {
    searchParams.set('sort_by', sort.field)
    searchParams.set('sort_desc', sort.descending.toString())
  }

  return fetchJson<PaginatedMarkets>(`${API_BASE}/markets?${searchParams}`, signal)
}

export async function getMarket(conditionId: string, signal?: AbortSignal): Promise<Market> {
  return fetchJson<Market>(`${API_BASE}/markets/${encodeURIComponent(conditionId)}`, signal)
}

export async function searchMarkets(query: string, limit = 20, signal?: AbortSignal): Promise<Market[]> {
  const searchParams = new URLSearchParams({ q: query, limit: limit.toString() })
  return fetchJson<Market[]>(`${API_BASE}/markets/search?${searchParams}`, signal)
}

export async function getCategories(resolved?: boolean, signal?: AbortSignal): Promise<CategoryCounts> {
  const params = new URLSearchParams()
  if (resolved !== undefined) {
    params.set('resolved', resolved.toString())
  }
  const queryString = params.toString()
  return fetchJson<CategoryCounts>(`${API_BASE}/categories${queryString ? '?' + queryString : ''}`, signal)
}

export async function getVolumeLeaders(category?: string, limit = 10, signal?: AbortSignal): Promise<Market[]> {
  const searchParams = new URLSearchParams({ limit: limit.toString() })
  if (category) {
    searchParams.set('category', category)
  }
  return fetchJson<Market[]>(`${API_BASE}/markets/leaders/volume?${searchParams}`, signal)
}

export async function getEventMarkets(eventId: string, signal?: AbortSignal): Promise<Market[]> {
  return fetchJson<Market[]>(`${API_BASE}/events/${encodeURIComponent(eventId)}/markets`, signal)
}
