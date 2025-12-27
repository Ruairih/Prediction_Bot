/**
 * Market Explorer TypeScript Types
 *
 * These types match the API response schemas from the FastAPI backend.
 */

export interface PriceData {
  yes_price: string
  no_price: string
  best_bid: string | null
  best_ask: string | null
  spread: string | null
  mid_price: string | null
}

export interface LiquidityData {
  volume_24h: string
  volume_7d: string
  open_interest: string
  liquidity_score: string
}

/** Market status values that match the backend enum */
export type MarketStatusValue = 'active' | 'resolving' | 'resolved' | 'cancelled'

export interface Market {
  condition_id: string
  question: string
  market_id: string | null
  event_id: string | null
  description: string | null
  category: string | null
  auto_category: string | null
  end_time: string | null
  resolved: boolean
  outcome: string | null
  status: MarketStatusValue
  price: PriceData | null
  liquidity: LiquidityData | null
}

export interface PaginatedMarkets {
  items: Market[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

/** Sortable fields that match the backend's allowed sort fields */
export type SortField =
  | 'volume_24h'
  | 'volume_7d'
  | 'liquidity_score'
  | 'yes_price'
  | 'end_time'
  | 'open_interest'
  | 'created_at'

export interface MarketFilter {
  categories?: string[]
  status?: MarketStatusValue[]
  min_price?: number
  max_price?: number
  min_volume_24h?: number
  min_liquidity_score?: number
  search?: string
  resolved?: boolean
}

export interface SortConfig {
  field: SortField
  descending: boolean
}

export type CategoryCounts = Record<string, number>
