/**
 * Tests for API client
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { listMarkets, getMarket, searchMarkets, getCategories } from '../src/api/client'
import type { Market, PaginatedMarkets, CategoryCounts } from '../src/types/market'

const mockMarket: Market = {
  condition_id: '0x001',
  question: 'Test market?',
  market_id: null,
  event_id: null,
  description: null,
  category: 'test',
  auto_category: null,
  end_time: '2025-12-31T23:59:59Z',
  resolved: false,
  outcome: null,
  status: 'active',
  price: {
    yes_price: '0.50',
    no_price: '0.50',
    best_bid: '0.49',
    best_ask: '0.51',
    spread: '0.02',
    mid_price: '0.50',
  },
  liquidity: {
    volume_24h: '10000',
    volume_7d: '50000',
    open_interest: '100000',
    liquidity_score: '75',
  },
}

const mockPaginatedResponse: PaginatedMarkets = {
  items: [mockMarket],
  total: 1,
  page: 1,
  page_size: 50,
  total_pages: 1,
  has_next: false,
  has_prev: false,
}

describe('API Client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('listMarkets', () => {
    it('fetches markets with default params', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPaginatedResponse),
      } as Response)

      const result = await listMarkets()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/markets?'),
        expect.objectContaining({})
      )
      expect(result).toEqual(mockPaginatedResponse)
    })

    it('includes filter params in request', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPaginatedResponse),
      } as Response)

      await listMarkets({
        filter: {
          categories: ['crypto', 'politics'],
          min_price: 0.2,
          search: 'bitcoin',
        },
      })

      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string
      expect(calledUrl).toContain('categories=crypto%2Cpolitics')
      expect(calledUrl).toContain('min_price=0.2')
      expect(calledUrl).toContain('search=bitcoin')
    })

    it('includes pagination params', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPaginatedResponse),
      } as Response)

      await listMarkets({ page: 3, pageSize: 25 })

      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string
      expect(calledUrl).toContain('page=3')
      expect(calledUrl).toContain('page_size=25')
    })

    it('includes sort params', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPaginatedResponse),
      } as Response)

      await listMarkets({
        sort: { field: 'liquidity_score', descending: false },
      })

      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string
      expect(calledUrl).toContain('sort_by=liquidity_score')
      expect(calledUrl).toContain('sort_desc=false')
    })

    it('throws on API error', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      } as Response)

      await expect(listMarkets()).rejects.toThrow('API Error: 500')
    })
  })

  describe('getMarket', () => {
    it('fetches single market by ID', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMarket),
      } as Response)

      const result = await getMarket('0x001')

      expect(fetch).toHaveBeenCalledWith('/api/markets/0x001', expect.objectContaining({}))
      expect(result).toEqual(mockMarket)
    })

    it('encodes special characters in ID', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMarket),
      } as Response)

      await getMarket('0x001/test')

      expect(fetch).toHaveBeenCalledWith('/api/markets/0x001%2Ftest', expect.objectContaining({}))
    })
  })

  describe('searchMarkets', () => {
    it('searches with query parameter', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([mockMarket]),
      } as Response)

      await searchMarkets('bitcoin', 10)

      const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string
      expect(calledUrl).toContain('q=bitcoin')
      expect(calledUrl).toContain('limit=10')
    })
  })

  describe('getCategories', () => {
    it('fetches category counts', async () => {
      const mockCategories: CategoryCounts = {
        crypto: 100,
        politics: 50,
        sports: 25,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockCategories),
      } as Response)

      const result = await getCategories()

      expect(fetch).toHaveBeenCalledWith('/api/categories', expect.objectContaining({}))
      expect(result).toEqual(mockCategories)
    })
  })
})
