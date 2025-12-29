import { useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMarkets, useCategories, useCategoriesDetailed, useEventMarkets } from '../hooks/useMarkets'
import { MarketTable } from '../components/MarketTable'
import { Search, Filter, RefreshCw, ChevronDown, ChevronUp, X, Grid, TrendingUp } from 'lucide-react'
import type { MarketFilter, SortConfig, SortField, CategoryDetail } from '../types/market'

const SORT_OPTIONS: Array<{ field: SortField; label: string }> = [
  { field: 'volume_24h', label: 'Volume (24h)' },
  { field: 'volume_num', label: 'Total Volume' },
  { field: 'liquidity_score', label: 'Liquidity' },
  { field: 'spread', label: 'Spread' },
  { field: 'yes_price', label: 'Price' },
  { field: 'end_time', label: 'End Time' },
]

const PAGE_SIZE_OPTIONS = [50, 100, 200, 500]

export function MarketsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const eventId = searchParams.get('event')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(200)
  const [filter, setFilter] = useState<MarketFilter>({ resolved: false })
  const [sort, setSort] = useState<SortConfig>({ field: 'volume_24h', descending: true })
  const [showFilters, setShowFilters] = useState(true)
  const [searchInput, setSearchInput] = useState('')

  // Category browser modal state
  const [showCategoryModal, setShowCategoryModal] = useState(false)
  const [categoryPage, setCategoryPage] = useState(1)
  const [categorySearch, setCategorySearch] = useState('')
  const [categorySearchInput, setCategorySearchInput] = useState('')

  // Fetch regular markets or event-specific markets
  const { data, isLoading, isFetching, refetch } = useMarkets(filter, sort, page, pageSize)
  const { data: eventMarkets, isLoading: eventLoading, isFetching: eventFetching, refetch: refetchEvent } = useEventMarkets(eventId)

  // Use event markets when filtering by event, otherwise use paginated markets
  const displayMarkets = eventId ? eventMarkets : data?.items
  const isLoadingMarkets = eventId ? eventLoading : isLoading
  const isFetchingMarkets = eventId ? eventFetching : isFetching
  const refetchMarkets = eventId ? refetchEvent : refetch

  const clearEventFilter = () => {
    setSearchParams({})
  }
  const { data: categories } = useCategories(filter.resolved)
  const { data: detailedCategories, isLoading: categoriesLoading } = useCategoriesDetailed(
    categoryPage,
    50,
    categorySearch || undefined,
    1
  )

  // Sort categories by count for better display
  const sortedCategories = useMemo(() => {
    if (!categories) return []
    return Object.entries(categories)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20) // Top 20 categories
  }, [categories])

  const handleSearch = () => {
    setFilter((prev) => ({
      ...prev,
      search: searchInput || undefined,
    }))
    setPage(1)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const handleCategoryChange = (category: string) => {
    setFilter((prev) => {
      const current = prev.categories || []
      const next = current.includes(category)
        ? current.filter((c) => c !== category)
        : [...current, category]
      return { ...prev, categories: next.length > 0 ? next : undefined }
    })
    setPage(1)
  }

  const handleResolvedToggle = () => {
    setFilter((prev) => ({
      ...prev,
      resolved: prev.resolved === undefined ? false : prev.resolved ? undefined : true,
    }))
    setPage(1)
  }

  const handleSortChange = (field: SortField) => {
    setSort((prev) => ({
      field,
      descending: prev.field === field ? !prev.descending : true,
    }))
    setPage(1)
  }

  const clearFilters = () => {
    setFilter({ resolved: false })
    setSearchInput('')
    setPage(1)
  }

  const activeFilterCount = [
    filter.categories?.length,
    filter.status?.length,
    filter.min_price !== undefined ? 1 : 0,
    filter.max_price !== undefined ? 1 : 0,
    filter.search ? 1 : 0,
  ].reduce((a, b) => (a || 0) + (b || 0), 0)

  return (
    <div className="space-y-3">
      {/* Event Filter Banner */}
      {eventId && (
        <div className="bg-pm-green/20 border border-pm-green/50 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-pm-green font-medium">Filtering by event</span>
            <span className="text-gray-300">
              Showing {eventMarkets?.length || 0} markets in this event
            </span>
          </div>
          <button
            onClick={clearEventFilter}
            className="flex items-center gap-2 px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
          >
            <X className="w-4 h-4" />
            Clear event filter
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Polymarket Explorer</h1>
          <p className="text-gray-400 text-sm">
            {eventId
              ? `${eventMarkets?.length || 0} markets in event`
              : `${data?.total.toLocaleString() || 0} markets • Page ${data?.page || 1} of ${data?.total_pages || 1}`
            }
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Page Size - only show when not filtering by event */}
          {!eventId && (
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
              className="bg-gray-700 rounded-lg px-3 py-2 text-sm"
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>{size} per page</option>
              ))}
            </select>
          )}

          <button
            onClick={() => refetchMarkets()}
            disabled={isFetchingMarkets}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600
                     rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetchingMarkets ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          {!eventId && (
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors
                        ${showFilters ? 'bg-pm-green text-black' : 'bg-gray-700 hover:bg-gray-600'}`}
            >
              <Filter className="w-4 h-4" />
              Filters {activeFilterCount ? `(${activeFilterCount})` : ''}
            </button>
          )}
        </div>
      </div>

      {/* Search Bar - Hide when filtering by event */}
      {!eventId && (
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search markets... (press Enter)"
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
      )}

      {/* Sort Controls - Hide when filtering by event */}
      {!eventId && (
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-400">Sort by:</span>
          {SORT_OPTIONS.map((option) => (
            <button
              key={option.field}
              onClick={() => handleSortChange(option.field)}
              className={`flex items-center gap-1 px-3 py-1 rounded-lg transition-colors
                        ${sort.field === option.field
                          ? 'bg-pm-green text-black'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
            >
              {option.label}
              {sort.field === option.field && (
                sort.descending ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />
              )}
            </button>
          ))}

          {/* Resolved Toggle */}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-gray-400">Show:</span>
            <button
              onClick={handleResolvedToggle}
              className={`px-3 py-1 rounded-lg text-sm transition-colors
                        ${filter.resolved === false
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
            >
              Active
            </button>
            <button
              onClick={() => setFilter((prev) => ({ ...prev, resolved: true }))}
              className={`px-3 py-1 rounded-lg text-sm transition-colors
                        ${filter.resolved === true
                          ? 'bg-purple-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
            >
              Resolved
            </button>
            <button
              onClick={() => setFilter((prev) => ({ ...prev, resolved: undefined }))}
              className={`px-3 py-1 rounded-lg text-sm transition-colors
                        ${filter.resolved === undefined
                          ? 'bg-gray-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
            >
              All
            </button>
          </div>
        </div>
      )}

      {/* Filters Panel - Hide when filtering by event */}
      {!eventId && showFilters && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 space-y-4">
          {/* Categories */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-300">
                Categories (top 20 by count)
              </h3>
              <button
                onClick={() => setShowCategoryModal(true)}
                className="flex items-center gap-1 text-xs text-pm-green hover:text-green-400 transition-colors"
              >
                <Grid className="w-3 h-3" />
                Browse all {detailedCategories?.total || '...'} categories
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {sortedCategories.map(([cat, count]) => (
                <button
                  key={cat}
                  onClick={() => handleCategoryChange(cat)}
                  className={`px-3 py-1 rounded-full text-xs transition-colors
                            ${filter.categories?.includes(cat)
                              ? 'bg-pm-green text-black'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                            }`}
                >
                  {cat} ({count})
                </button>
              ))}
            </div>
          </div>

          {/* Price Range */}
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-300">Min Price</label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={filter.min_price || ''}
                onChange={(e) => {
                  setFilter({
                    ...filter,
                    min_price: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                  setPage(1)
                }}
                className="w-full mt-1 bg-gray-700 rounded px-3 py-2 text-sm"
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-300">Max Price</label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={filter.max_price || ''}
                onChange={(e) => {
                  setFilter({
                    ...filter,
                    max_price: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                  setPage(1)
                }}
                className="w-full mt-1 bg-gray-700 rounded px-3 py-2 text-sm"
                placeholder="1.00"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-300">Min Volume (24h)</label>
              <input
                type="number"
                min="0"
                step="1000"
                value={filter.min_volume_24h || ''}
                onChange={(e) => {
                  setFilter({
                    ...filter,
                    min_volume_24h: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                  setPage(1)
                }}
                className="w-full mt-1 bg-gray-700 rounded px-3 py-2 text-sm"
                placeholder="0"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-300">Min Liquidity</label>
              <input
                type="number"
                min="0"
                step="1000"
                value={filter.min_liquidity_score || ''}
                onChange={(e) => {
                  setFilter({
                    ...filter,
                    min_liquidity_score: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                  setPage(1)
                }}
                className="w-full mt-1 bg-gray-700 rounded px-3 py-2 text-sm"
                placeholder="0"
              />
            </div>
          </div>

          {/* Clear button */}
          <div className="flex justify-end">
            <button
              onClick={clearFilters}
              className="text-sm text-gray-400 hover:text-white"
            >
              Clear all filters
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <MarketTable markets={displayMarkets || []} isLoading={isLoadingMarkets} />

      {/* Pagination - Hide when filtering by event */}
      {!eventId && data && data.total_pages > 1 && (
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
            Page {data.page} of {data.total_pages} ({data.total.toLocaleString()} total)
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

      {/* Category Browser Modal */}
      {showCategoryModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-4xl max-h-[85vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div>
                <h2 className="text-xl font-bold text-white">All Categories</h2>
                <p className="text-gray-400 text-sm">
                  {detailedCategories?.total.toLocaleString() || 0} categories •
                  Page {detailedCategories?.page || 1} of {detailedCategories?.total_pages || 1}
                </p>
              </div>
              <button
                onClick={() => {
                  setShowCategoryModal(false)
                  setCategorySearch('')
                  setCategorySearchInput('')
                  setCategoryPage(1)
                }}
                className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Search Bar */}
            <div className="p-4 border-b border-gray-700">
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={categorySearchInput}
                    onChange={(e) => setCategorySearchInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        setCategorySearch(categorySearchInput)
                        setCategoryPage(1)
                      }
                    }}
                    placeholder="Search categories..."
                    className="w-full bg-gray-800 rounded-lg pl-10 pr-4 py-2 text-sm border border-gray-700
                             focus:border-pm-green focus:outline-none"
                  />
                </div>
                <button
                  onClick={() => {
                    setCategorySearch(categorySearchInput)
                    setCategoryPage(1)
                  }}
                  className="px-4 py-2 bg-pm-green text-black rounded-lg text-sm font-medium hover:bg-green-400"
                >
                  Search
                </button>
                {categorySearch && (
                  <button
                    onClick={() => {
                      setCategorySearch('')
                      setCategorySearchInput('')
                      setCategoryPage(1)
                    }}
                    className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg text-sm hover:bg-gray-600"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            {/* Categories Grid */}
            <div className="flex-1 overflow-y-auto p-4">
              {categoriesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-8 h-8 animate-spin text-pm-green" />
                </div>
              ) : detailedCategories?.items.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  No categories found {categorySearch && `matching "${categorySearch}"`}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {detailedCategories?.items.map((cat: CategoryDetail) => (
                    <button
                      key={cat.category}
                      onClick={() => {
                        handleCategoryChange(cat.category)
                        setShowCategoryModal(false)
                        setCategorySearch('')
                        setCategorySearchInput('')
                        setCategoryPage(1)
                      }}
                      className={`p-3 rounded-lg text-left transition-all hover:scale-[1.02]
                                ${filter.categories?.includes(cat.category)
                                  ? 'bg-pm-green/20 border-2 border-pm-green'
                                  : 'bg-gray-800 border border-gray-700 hover:border-gray-600'
                                }`}
                    >
                      <div className="font-medium text-white truncate">{cat.category}</div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                        <span>{cat.market_count} markets</span>
                        <span className="flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" />
                          ${(cat.total_volume_24h / 1000).toFixed(1)}k vol
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        ${(cat.total_liquidity / 1000).toFixed(1)}k liquidity
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Pagination */}
            {detailedCategories && detailedCategories.total_pages > 1 && (
              <div className="flex items-center justify-center gap-4 p-4 border-t border-gray-700">
                <button
                  onClick={() => setCategoryPage(1)}
                  disabled={categoryPage === 1}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  First
                </button>
                <button
                  onClick={() => setCategoryPage((p) => Math.max(1, p - 1))}
                  disabled={categoryPage === 1}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  Previous
                </button>
                <span className="text-gray-400 text-sm">
                  Page {detailedCategories.page} of {detailedCategories.total_pages}
                </span>
                <button
                  onClick={() => setCategoryPage((p) => p + 1)}
                  disabled={categoryPage >= detailedCategories.total_pages}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  Next
                </button>
                <button
                  onClick={() => setCategoryPage(detailedCategories.total_pages)}
                  disabled={categoryPage === detailedCategories.total_pages}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  Last
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
