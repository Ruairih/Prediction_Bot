import { useParams, Link } from 'react-router-dom'
import { useMarket } from '../hooks/useMarkets'
import { ArrowLeft, ExternalLink, Star, Clock } from 'lucide-react'

function formatPrice(price: string | null | undefined): string {
  if (!price) return '-'
  return `$${parseFloat(price).toFixed(2)}`
}

function formatVolume(volume: string | null | undefined): string {
  if (!volume) return '-'
  const num = parseFloat(volume)
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`
  if (num >= 1_000) return `$${(num / 1_000).toFixed(2)}K`
  return `$${num.toFixed(2)}`
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'No expiry'
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getDaysUntil(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const now = new Date()
  const diff = date.getTime() - now.getTime()
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24))
  if (days < 0) return 'Expired'
  if (days === 0) return 'Today'
  if (days === 1) return '1 day'
  return `${days} days`
}

export function MarketDetailPage() {
  const { conditionId } = useParams<{ conditionId: string }>()
  const { data: market, isLoading, error } = useMarket(conditionId || '')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading market details...</div>
      </div>
    )
  }

  if (error || !market) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="text-red-400">Market not found</div>
        <Link to="/" className="text-pm-green hover:underline">
          Back to markets
        </Link>
      </div>
    )
  }

  const spread = market.price?.spread
    ? (parseFloat(market.price.spread) * 100).toFixed(1)
    : null

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back button */}
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to markets
      </Link>

      {/* Header */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-white mb-2">{market.question}</h1>
            {market.description && (
              <p className="text-gray-400">{market.description}</p>
            )}
          </div>
          <button className="p-2 hover:bg-gray-700 rounded-lg">
            <Star className="w-6 h-6 text-gray-400" />
          </button>
        </div>

        {/* Status badges */}
        <div className="flex items-center gap-3 mt-4">
          <span
            className={`badge ${
              market.status === 'active'
                ? 'badge-active'
                : market.status === 'resolving'
                ? 'badge-resolving'
                : 'badge-resolved'
            }`}
          >
            {market.status}
          </span>
          {market.category && (
            <span className="badge bg-gray-700 text-gray-300 capitalize">
              {market.category}
            </span>
          )}
          {market.end_time && (
            <span className="flex items-center gap-1 text-sm text-gray-400">
              <Clock className="w-4 h-4" />
              {getDaysUntil(market.end_time)}
            </span>
          )}
        </div>
      </div>

      {/* Price section */}
      <div className="grid grid-cols-2 gap-6">
        {/* YES side */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-2">YES Price</div>
          <div className="text-4xl font-bold text-pm-green">
            {formatPrice(market.price?.yes_price)}
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Best Bid</span>
              <span>{formatPrice(market.price?.best_bid)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Best Ask</span>
              <span>{formatPrice(market.price?.best_ask)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Spread</span>
              <span>{spread ? `${spread}%` : '-'}</span>
            </div>
          </div>
        </div>

        {/* NO side */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-2">NO Price</div>
          <div className="text-4xl font-bold text-pm-red">
            {formatPrice(market.price?.no_price)}
          </div>
        </div>
      </div>

      {/* Stats section */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Market Statistics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <div className="text-sm text-gray-400">Volume (24h)</div>
            <div className="text-xl font-mono">
              {formatVolume(market.liquidity?.volume_24h)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Volume (7d)</div>
            <div className="text-xl font-mono">
              {formatVolume(market.liquidity?.volume_7d)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Open Interest</div>
            <div className="text-xl font-mono">
              {formatVolume(market.liquidity?.open_interest)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Liquidity Score</div>
            <div className="text-xl font-mono">
              {market.liquidity?.liquidity_score || '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Timing section */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Timing</h2>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="text-sm text-gray-400">Expires</div>
            <div className="text-lg">{formatDate(market.end_time)}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Time Remaining</div>
            <div className="text-lg">{getDaysUntil(market.end_time)}</div>
          </div>
        </div>
      </div>

      {/* External link */}
      <div className="flex justify-end">
        <a
          href={`https://polymarket.com/market/${market.condition_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-pm-green hover:underline"
        >
          View on Polymarket
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </div>
  )
}
