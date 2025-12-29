import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, RefreshCw, ChevronDown, ChevronUp, ExternalLink, TrendingUp, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

interface Event {
  event_id: string
  title: string
  slug: string | null
  description: string | null
  category: string | null
  image: string | null
  start_date: string | null
  end_date: string | null
  volume: number
  volume_24h: number
  volume_7d: number
  liquidity: number
  market_count: number
  active_market_count: number
  active: boolean
  closed: boolean
}

interface PaginatedEvents {
  items: Event[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

const SORT_OPTIONS = [
  { field: 'volume', label: 'Total Volume' },
  { field: 'volume_24h', label: 'Volume (24h)' },
  { field: 'volume_7d', label: 'Volume (7d)' },
  { field: 'market_count', label: 'Markets' },
  { field: 'liquidity', label: 'Liquidity' },
]

async function fetchEvents(params: {
  page: number
  pageSize: number
  search?: string
  sortBy: string
  sortDesc: boolean
}): Promise<PaginatedEvents> {
  const searchParams = new URLSearchParams()
  searchParams.set('page', params.page.toString())
  searchParams.set('page_size', params.pageSize.toString())
  searchParams.set('sort_by', params.sortBy)
  searchParams.set('sort_desc', params.sortDesc.toString())
  if (params.search) {
    searchParams.set('search', params.search)
  }

  const response = await fetch(`/api/events?${searchParams}`)
  if (!response.ok) {
    throw new Error('Failed to fetch events')
  }
  return response.json()
}

function formatVolume(volume: number): string {
  if (volume >= 1e9) return `$${(volume / 1e9).toFixed(1)}B`
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(1)}M`
  if (volume >= 1e3) return `$${(volume / 1e3).toFixed(1)}K`
  return `$${volume.toFixed(0)}`
}

export function EventsPage() {
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('volume')
  const [sortDesc, setSortDesc] = useState(true)

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['events', page, pageSize, search, sortBy, sortDesc],
    queryFn: () => fetchEvents({ page, pageSize, search: search || undefined, sortBy, sortDesc }),
  })

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(1)
  }

  const handleSortChange = (field: string) => {
    if (sortBy === field) {
      setSortDesc(!sortDesc)
    } else {
      setSortBy(field)
      setSortDesc(true)
    }
    setPage(1)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Events</h1>
          <p className="text-gray-400 text-sm">
            Aggregated view of market groups • {data?.total.toLocaleString() || 0} events
          </p>
        </div>

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600
                   rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search events... (press Enter)"
            className="w-full bg-gray-800 rounded-lg pl-10 pr-4 py-2 text-sm border border-gray-700
                     focus:border-pm-green focus:outline-none"
          />
        </div>
        <button
          onClick={handleSearch}
          className="px-4 py-2 bg-pm-green text-black rounded-lg text-sm font-medium hover:bg-green-400"
        >
          Search
        </button>
      </div>

      {/* Sort Controls */}
      <div className="flex items-center gap-4 text-sm">
        <span className="text-gray-400">Sort by:</span>
        {SORT_OPTIONS.map((option) => (
          <button
            key={option.field}
            onClick={() => handleSortChange(option.field)}
            className={`flex items-center gap-1 px-3 py-1 rounded-lg transition-colors
                      ${sortBy === option.field
                        ? 'bg-pm-green text-black'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
          >
            {option.label}
            {sortBy === option.field && (
              sortDesc ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />
            )}
          </button>
        ))}
      </div>

      {/* Events List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-pm-green" />
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No events found {search && `matching "${search}"`}
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map((event) => (
            <div
              key={event.event_id}
              className="bg-gray-800 rounded-lg border border-gray-700 p-4 hover:border-gray-600 transition-colors"
            >
              <div className="flex items-start gap-4">
                {/* Event Image */}
                {event.image && (
                  <img
                    src={event.image}
                    alt={event.title}
                    className="w-16 h-16 rounded-lg object-cover flex-shrink-0"
                  />
                )}

                {/* Event Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-semibold text-white truncate">{event.title}</h3>
                      {event.description && (
                        <p className="text-gray-400 text-sm line-clamp-2 mt-1">
                          {event.description}
                        </p>
                      )}
                    </div>

                    {/* Polymarket Link */}
                    {event.slug && (
                      <a
                        href={`https://polymarket.com/event/${event.slug}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-pm-green hover:text-green-400 text-sm flex-shrink-0"
                      >
                        <ExternalLink className="w-4 h-4" />
                        View on Polymarket
                      </a>
                    )}
                  </div>

                  {/* Metrics */}
                  <div className="flex flex-wrap items-center gap-6 mt-3 text-sm">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-pm-green" />
                      <span className="text-white font-medium">{formatVolume(event.volume)}</span>
                      <span className="text-gray-500">total volume</span>
                    </div>

                    <div>
                      <span className="text-gray-400">24h: </span>
                      <span className="text-white">{formatVolume(event.volume_24h)}</span>
                    </div>

                    <div>
                      <span className="text-gray-400">7d: </span>
                      <span className="text-white">{formatVolume(event.volume_7d)}</span>
                    </div>

                    <div className="flex items-center gap-1">
                      <Users className="w-4 h-4 text-gray-400" />
                      <span className="text-white">{event.market_count}</span>
                      <span className="text-gray-500">markets</span>
                      {event.active_market_count < event.market_count && (
                        <span className="text-gray-500">({event.active_market_count} active)</span>
                      )}
                    </div>

                    <div>
                      <span className="text-gray-400">Liquidity: </span>
                      <span className="text-white">{formatVolume(event.liquidity)}</span>
                    </div>
                  </div>

                  {/* View Markets Link */}
                  <div className="mt-3">
                    <Link
                      to={`/?event=${event.event_id}`}
                      className="text-sm text-pm-green hover:text-green-400"
                    >
                      View all {event.market_count} markets in this event →
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-4 py-4">
          <button
            onClick={() => setPage(1)}
            disabled={page === 1}
            className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
          >
            First
          </button>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!data.has_prev}
            className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
          >
            Previous
          </button>
          <span className="text-gray-400 text-sm">
            Page {data.page} of {data.total_pages} ({data.total.toLocaleString()} events)
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!data.has_next}
            className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
          >
            Next
          </button>
          <button
            onClick={() => setPage(data.total_pages)}
            disabled={page === data.total_pages}
            className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
          >
            Last
          </button>
        </div>
      )}
    </div>
  )
}
