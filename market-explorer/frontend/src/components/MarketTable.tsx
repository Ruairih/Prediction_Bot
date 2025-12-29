import { useMemo, useRef, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ColumnFiltersState,
  type SortingFn,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Star, ChevronUp, ChevronDown, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Market, MarketStatusValue } from '../types/market'

interface MarketTableProps {
  markets: Market[]
  isLoading?: boolean
}

const columnHelper = createColumnHelper<Market>()

// Numeric sorting function for string values (prices, volumes, etc.)
const numericSort: SortingFn<Market> = (rowA, rowB, columnId) => {
  const a = rowA.getValue<string | null | undefined>(columnId)
  const b = rowB.getValue<string | null | undefined>(columnId)

  // Handle null/undefined - push them to the end
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1

  const numA = parseFloat(a)
  const numB = parseFloat(b)

  // Handle NaN
  if (isNaN(numA) && isNaN(numB)) return 0
  if (isNaN(numA)) return 1
  if (isNaN(numB)) return -1

  return numA - numB
}

function formatVolume(volume: string | null | undefined): string {
  if (!volume) return '-'
  const num = parseFloat(volume)
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(1)}M`
  if (num >= 1_000) return `$${(num / 1_000).toFixed(0)}K`
  return `$${num.toFixed(0)}`
}

function formatSpread(spread: string | null | undefined): string {
  if (!spread) return '-'
  const num = parseFloat(spread)
  return `${(num * 100).toFixed(1)}%`
}

function formatEndTime(endTime: string | null | undefined): string {
  if (!endTime) return '-'
  const date = new Date(endTime)
  const now = new Date()
  const diff = date.getTime() - now.getTime()

  if (diff < 0) return 'Ended'

  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))

  if (days > 30) {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h`

  const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
  return `${mins}m`
}

function StatusBadge({ status }: { status: MarketStatusValue }) {
  const classes: Record<MarketStatusValue, string> = {
    active: 'badge-active',
    resolving: 'badge-resolving',
    resolved: 'badge-resolved',
    cancelled: 'bg-red-900 text-red-300',
  }
  return (
    <span className={`badge ${classes[status]}`}>
      {status}
    </span>
  )
}

function PriceBar({ price }: { price: string | null | undefined }) {
  if (!price) return <div className="w-16 h-2 bg-gray-700 rounded" />
  const num = parseFloat(price)
  const pct = Math.min(num * 100, 100)
  const color = num > 0.8 ? 'bg-green-500' : num > 0.5 ? 'bg-yellow-500' : num > 0.2 ? 'bg-orange-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1.5 bg-gray-700 rounded overflow-hidden">
        <div
          className={`h-full ${color} rounded`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs">{(num * 100).toFixed(0)}¢</span>
    </div>
  )
}

const ROW_HEIGHT = 40

export function MarketTable({ markets, isLoading }: MarketTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set())
  const parentRef = useRef<HTMLDivElement>(null)

  const toggleWatchlist = (id: string) => {
    setWatchlist((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'watchlist',
        header: () => null,
        cell: ({ row }) => (
          <button
            onClick={() => toggleWatchlist(row.original.condition_id)}
            className="p-0.5 hover:bg-gray-700 rounded"
          >
            <Star
              className={`w-3 h-3 ${
                watchlist.has(row.original.condition_id)
                  ? 'fill-yellow-400 text-yellow-400'
                  : 'text-gray-600'
              }`}
            />
          </button>
        ),
        size: 28,
      }),
      columnHelper.accessor('question', {
        header: 'Market',
        cell: ({ getValue, row }) => (
          <div className="flex items-center gap-1">
            <Link
              to={`/markets/${row.original.condition_id}`}
              className="hover:text-pm-green transition-colors line-clamp-1 text-sm"
              title={getValue()}
            >
              {getValue()}
            </Link>
            <a
              href={`https://polymarket.com/event/${row.original.event_id || row.original.condition_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 hover:text-pm-green"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        ),
        size: 380,
      }),
      columnHelper.accessor((row) => row.price?.yes_price, {
        id: 'yes_price',
        header: 'YES Price',
        cell: ({ getValue }) => <PriceBar price={getValue()} />,
        sortingFn: numericSort,
        size: 100,
      }),
      columnHelper.accessor((row) => row.price?.spread, {
        id: 'spread',
        header: 'Spread',
        cell: ({ getValue }) => (
          <span className="text-gray-400 text-xs">{formatSpread(getValue())}</span>
        ),
        sortingFn: numericSort,
        size: 60,
      }),
      columnHelper.accessor((row) => row.liquidity?.volume_24h, {
        id: 'volume_24h',
        header: 'Vol 24h',
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatVolume(getValue())}</span>
        ),
        sortingFn: numericSort,
        size: 80,
      }),
      columnHelper.accessor((row) => row.liquidity?.liquidity_score, {
        id: 'liquidity',
        header: 'Liquidity',
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatVolume(getValue())}</span>
        ),
        sortingFn: numericSort,
        size: 80,
      }),
      columnHelper.accessor('end_time', {
        header: 'Ends',
        cell: ({ getValue }) => (
          <span className="text-gray-400 text-xs">{formatEndTime(getValue())}</span>
        ),
        size: 70,
      }),
      columnHelper.accessor('category', {
        header: 'Category',
        cell: ({ getValue }) => (
          <span className="text-gray-400 text-xs capitalize truncate max-w-[80px] block">{getValue() || '-'}</span>
        ),
        size: 90,
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        cell: ({ getValue }) => <StatusBadge status={getValue()} />,
        size: 70,
      }),
    ],
    [watchlist]
  )

  const table = useReactTable({
    data: markets,
    columns,
    state: {
      sorting,
      columnFilters,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const { rows } = table.getRowModel()

  // Virtual scrolling for performance with large lists
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Loading markets...
      </div>
    )
  }

  const virtualRows = virtualizer.getVirtualItems()
  const totalHeight = virtualizer.getTotalSize()

  // Padding to position virtual rows correctly
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0
  const paddingBottom =
    virtualRows.length > 0
      ? totalHeight - (virtualRows[virtualRows.length - 1]?.end ?? 0)
      : 0

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <div
        ref={parentRef}
        className="overflow-auto max-h-[calc(100vh-280px)]"
      >
        <table className="w-full table-dense">
          <thead className="bg-gray-750 sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="text-left text-gray-400 font-medium border-b border-gray-700 text-xs py-2 px-2"
                    style={{ width: header.getSize() }}
                  >
                    {header.isPlaceholder ? null : (
                      <div
                        className={`flex items-center gap-1 ${
                          header.column.getCanSort() ? 'cursor-pointer select-none hover:text-white' : ''
                        }`}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === 'asc' && <ChevronUp className="w-3 h-3" />}
                        {header.column.getIsSorted() === 'desc' && <ChevronDown className="w-3 h-3" />}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {/* Top spacer for virtual scrolling */}
            {paddingTop > 0 && (
              <tr>
                <td style={{ height: `${paddingTop}px` }} colSpan={columns.length} />
              </tr>
            )}
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index]
              return (
                <tr
                  key={row.id}
                  className="border-b border-gray-700/50 hover:bg-gray-750 transition-colors"
                  style={{ height: `${ROW_HEIGHT}px` }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-2 py-1"
                      style={{ width: cell.column.getSize() }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              )
            })}
            {/* Bottom spacer for virtual scrolling */}
            {paddingBottom > 0 && (
              <tr>
                <td style={{ height: `${paddingBottom}px` }} colSpan={columns.length} />
              </tr>
            )}
          </tbody>
        </table>

        {rows.length === 0 && (
          <div className="flex items-center justify-center h-32 text-gray-400">
            No markets found
          </div>
        )}
      </div>

      {/* Footer with count */}
      <div className="px-4 py-1.5 bg-gray-750 border-t border-gray-700 text-xs text-gray-400">
        Showing {rows.length} markets
      </div>
    </div>
  )
}
