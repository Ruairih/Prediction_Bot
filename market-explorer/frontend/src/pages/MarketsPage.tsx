import { useState, useMemo } from 'react'
import { useMarkets, useCategories } from '../hooks/useMarkets'
import { MarketTable } from '../components/MarketTable'
import { Search, Filter, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import type { MarketFilter, SortConfig, MarketStatusValue } from '../types/market'

const STATUS_OPTIONS: MarketStatusValue[] = ['active', 'resolving', 'resolved']

const SORT_OPTIONS = [
  { field: 'volume_24h', label: 'Volume (24h)' },
  { field: 'liquidity_score', label: 'Liquidity' },
  { field: 'yes_price', label: 'Price' },
  { field: 'end_time', label: 'End Time' },
]

const PAGE_SIZE_OPTIONS = [50, 100, 200, 500]

export function MarketsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(200)
  const [filter, setFilter] = useState<MarketFilter>({ resolved: false })
  const [sort, setSort] = useState<SortConfig>({ field: 'volume_24h', descending: true })
  const [showFilters, setShowFilters] = useState(true)
  const [searchInput, setSearchInput] = useState('')

  const { data, isLoading, isFetching, refetch } = useMarkets(filter, sort, page, pageSize)
  const { data: categories } = useCategories(filter.resolved)

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

  const handleStatusChange = (status: MarketStatusValue) => {
    setFilter((prev) => {
      const current = prev.status || []
      const next = current.includes(status)
        ? current.filter((s) => s !== status)
        : [...current, status]
      return { ...prev, status: next.length > 0 ? next : undefined }
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

  const handleSortChange = (field: string) => {
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Polymarket Explorer</h1>
          <p className="text-gray-400 text-sm">
            {data?.total.toLocaleString() || 0} markets • Page {data?.page || 1} of {data?.total_pages || 1}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Page Size */}
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

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600
                     rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors
                      ${showFilters ? 'bg-pm-green text-black' : 'bg-gray-700 hover:bg-gray-600'}`}
          >
            <Filter className="w-4 h-4" />
            Filters {activeFilterCount ? `(${activeFilterCount})` : ''}
          </button>
        </div>
      </div>

      {/* Search Bar - Always visible */}
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

      {/* Sort Controls - Always visible */}
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

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 space-y-4">
          {/* Categories */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">
              Categories (top 20 by count)
            </h3>
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
      <MarketTable markets={data?.items || []} isLoading={isLoading} />

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
    </div>
  )
}
