/**
 * Tests for MarketTable component
 *
 * Note: Virtual scrolling doesn't work in jsdom (no layout measurements).
 * These tests focus on the states and behaviors we can test without virtualization.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { MarketTable } from '../src/components/MarketTable'
import type { Market } from '../src/types/market'

function renderWithRouter(component: React.ReactNode) {
  return render(<BrowserRouter>{component}</BrowserRouter>)
}

const mockMarket: Market = {
  condition_id: '0x001',
  question: 'Will Bitcoin hit $150k by end of 2025?',
  market_id: null,
  event_id: null,
  description: null,
  category: 'crypto',
  auto_category: null,
  end_time: '2025-12-31T23:59:59Z',
  resolved: false,
  outcome: null,
  status: 'active',
  price: {
    yes_price: '0.42',
    no_price: '0.58',
    best_bid: '0.41',
    best_ask: '0.43',
    spread: '0.02',
    mid_price: '0.42',
  },
  liquidity: {
    volume_24h: '125000',
    volume_7d: '800000',
    open_interest: '1500000',
    liquidity_score: '85',
  },
}

describe('MarketTable', () => {
  it('renders loading state', () => {
    renderWithRouter(<MarketTable markets={[]} isLoading={true} />)
    expect(screen.getByText('Loading markets...')).toBeInTheDocument()
  })

  it('shows "No markets found" when empty and not loading', () => {
    renderWithRouter(<MarketTable markets={[]} isLoading={false} />)
    expect(screen.getByText('No markets found')).toBeInTheDocument()
  })

  it('renders table headers correctly', () => {
    renderWithRouter(<MarketTable markets={[mockMarket]} isLoading={false} />)

    // Check column headers are present
    expect(screen.getByText('Market')).toBeInTheDocument()
    expect(screen.getByText('YES')).toBeInTheDocument()
    expect(screen.getByText('Spread')).toBeInTheDocument()
    expect(screen.getByText('Vol 24h')).toBeInTheDocument()
    expect(screen.getByText('Liquidity')).toBeInTheDocument()
    expect(screen.getByText('Category')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('shows market count in footer', () => {
    const markets = [mockMarket]
    renderWithRouter(<MarketTable markets={markets} isLoading={false} />)
    expect(screen.getByText('Showing 1 markets')).toBeInTheDocument()
  })

  it('shows correct count for multiple markets', () => {
    const markets: Market[] = [
      { ...mockMarket, condition_id: '0x001' },
      { ...mockMarket, condition_id: '0x002' },
      { ...mockMarket, condition_id: '0x003' },
    ]
    renderWithRouter(<MarketTable markets={markets} isLoading={false} />)
    expect(screen.getByText('Showing 3 markets')).toBeInTheDocument()
  })

  it('shows zero count when empty', () => {
    renderWithRouter(<MarketTable markets={[]} isLoading={false} />)
    expect(screen.getByText('Showing 0 markets')).toBeInTheDocument()
  })
})

describe('MarketTable Table Structure', () => {
  it('renders a table element', () => {
    renderWithRouter(<MarketTable markets={[mockMarket]} isLoading={false} />)
    expect(document.querySelector('table')).toBeInTheDocument()
  })

  it('has dense table styling class', () => {
    renderWithRouter(<MarketTable markets={[mockMarket]} isLoading={false} />)
    expect(document.querySelector('table.table-dense')).toBeInTheDocument()
  })

  it('has sticky header', () => {
    renderWithRouter(<MarketTable markets={[mockMarket]} isLoading={false} />)
    const thead = document.querySelector('thead')
    expect(thead?.className).toContain('sticky')
  })
})
