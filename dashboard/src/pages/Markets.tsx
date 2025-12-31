/**
 * Markets Page
 * Market universe overview with quick detail panel.
 */
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { formatDistanceToNowStrict } from 'date-fns';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts';
import {
  useMarkets,
  useMarketDetail,
  useMarketHistory,
  useMarketOrderbook,
  useRisk,
  queryKeys,
} from '../hooks/useDashboardData';
import { blockMarket, unblockMarket, submitManualOrder } from '../api/dashboard';
import type { MarketSummary, OrderSide } from '../types';

export function Markets() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [selectedMarket, setSelectedMarket] = useState<MarketSummary | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);
  const [selectedTokenId, setSelectedTokenId] = useState<string | null>(null);

  const [orderSide, setOrderSide] = useState<OrderSide>('BUY');
  const [orderPrice, setOrderPrice] = useState('');
  const [orderSize, setOrderSize] = useState('');
  const [orderReason, setOrderReason] = useState('manual_entry');
  const [orderError, setOrderError] = useState<string | null>(null);
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null);
  const [orderSubmitting, setOrderSubmitting] = useState(false);

  // Read conditionId from URL for deep linking
  const urlConditionId = searchParams.get('conditionId');

  const { data: marketsData, isLoading, error } = useMarkets({ limit: 500 });
  const { data: riskData } = useRisk();
  const effectiveConditionId = selectedConditionId ?? selectedMarket?.conditionId ?? undefined;
  const { data: marketDetail } = useMarketDetail(effectiveConditionId);
  const { data: marketHistory } = useMarketHistory(effectiveConditionId, 100);
  const { data: marketOrderbook } = useMarketOrderbook(effectiveConditionId, selectedTokenId ?? undefined);
  const markets = marketsData ?? [];

  const tokens = marketDetail?.tokens ?? [];

  useEffect(() => {
    if (!tokens.length) {
      setSelectedTokenId(null);
      return;
    }
    if (!selectedTokenId || !tokens.some((token) => token.tokenId === selectedTokenId)) {
      setSelectedTokenId(tokens[0].tokenId);
    }
  }, [tokens, selectedTokenId]);

  useEffect(() => {
    setOrderPrice('');
    setOrderSize('');
    setOrderReason('manual_entry');
    setOrderError(null);
    setOrderSuccess(null);
  }, [effectiveConditionId]);

  // Auto-select market from URL conditionId
  useEffect(() => {
    if (urlConditionId) {
      setSelectedConditionId(urlConditionId);
    }
  }, [urlConditionId]);

  useEffect(() => {
    if (!selectedConditionId || markets.length === 0) {
      return;
    }
    const market = markets.find((m) => m.conditionId === selectedConditionId) ?? null;
    if (market?.conditionId !== selectedMarket?.conditionId) {
      setSelectedMarket(market);
    }
  }, [selectedConditionId, markets, selectedMarket]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    markets.forEach((market) => {
      if (market.category) {
        set.add(market.category);
      }
    });
    return ['all', ...Array.from(set).sort()];
  }, [markets]);

  const filteredMarkets = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return markets.filter((market) => {
      if (category !== 'all' && market.category !== category) {
        return false;
      }
      if (!normalizedSearch) {
        return true;
      }
      return market.question.toLowerCase().includes(normalizedSearch);
    });
  }, [markets, search, category]);

  const priceSeries = useMemo(() => {
    const history = marketHistory ?? [];
    return [...history]
      .filter((trade) => trade.timestamp)
      .reverse()
      .map((trade) => ({
        timestamp: trade.timestamp as string,
        price: trade.price,
      }));
  }, [marketHistory]);

  const sizePresets = useMemo(() => {
    const base = riskData?.limits.maxPositionSize ?? 0;
    if (base > 0) {
      return [base * 0.25, base * 0.5, base];
    }
    return [5, 10, 20];
  }, [riskData]);

  const handleSelect = (market: MarketSummary) => {
    setSelectedMarket(market);
    setSelectedConditionId(market.conditionId ?? null);
  };

  const handleManualOrder = async () => {
    setOrderError(null);
    setOrderSuccess(null);

    if (!selectedTokenId || !effectiveConditionId) {
      setOrderError('Select a market token before submitting.');
      return;
    }

    const price = Number(orderPrice);
    const size = Number(orderSize);

    if (!Number.isFinite(price) || price <= 0) {
      setOrderError('Enter a valid limit price.');
      return;
    }
    if (!Number.isFinite(size) || size <= 0) {
      setOrderError('Enter a valid order size.');
      return;
    }

    try {
      setOrderSubmitting(true);
      await submitManualOrder({
        tokenId: selectedTokenId,
        side: orderSide,
        price,
        size,
        conditionId: effectiveConditionId,
        reason: orderReason || 'manual_entry',
      });
      setOrderSuccess('Manual order submitted.');
      queryClient.invalidateQueries({ queryKey: queryKeys.orders });
      queryClient.invalidateQueries({ queryKey: queryKeys.activity });
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Manual order failed.');
    } finally {
      setOrderSubmitting(false);
    }
  };

  const detail = marketDetail?.market;
  const hasSelection = Boolean(selectedMarket || detail);
  const position = marketDetail?.position;
  const openOrders = marketDetail?.orders ?? [];
  const lastSignal = marketDetail?.lastSignal;
  const lastFill = marketDetail?.lastFill;
  const lastTrade = marketDetail?.lastTrade;
  const orderbook = marketOrderbook;

  const bestBid = marketOrderbook?.bestBid ?? detail?.bestBid ?? selectedMarket?.bestBid ?? null;
  const bestAsk = marketOrderbook?.bestAsk ?? detail?.bestAsk ?? selectedMarket?.bestAsk ?? null;

  return (
    <div className="px-6 py-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Markets
          </div>
          <h1 className="text-3xl font-semibold text-text-primary">Market Radar</h1>
          <p className="text-text-secondary">
            Scan live markets, liquidity, and pricing depth in one view.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search question or ticker"
            className="min-w-[220px] rounded-full border border-border bg-bg-secondary px-4 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-blue"
          />
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="rounded-full border border-border bg-bg-secondary px-4 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
          >
            {categories.map((option) => (
              <option key={option} value={option}>
                {option === 'all' ? 'All categories' : option}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-2xl p-4">
          <p className="text-accent-red">
            Unable to load markets. Make sure the ingestion pipeline is running.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6">
        <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="text-sm text-text-secondary">
              {filteredMarkets.length} markets
            </div>
            {isLoading && <span className="text-xs text-text-secondary">Refreshing...</span>}
          </div>
          {/* Horizontal scroll wrapper for mobile */}
          <div className="overflow-x-auto -webkit-overflow-scrolling-touch">
            <table className="w-full min-w-[700px] text-sm" aria-label="Markets list">
              <caption className="sr-only">
                Available markets showing market question, category, bid price, ask price, spread, and volume
              </caption>
              <thead className="bg-bg-tertiary text-text-secondary text-xs uppercase tracking-widest">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left">Market</th>
                  <th scope="col" className="px-4 py-3 text-left">Category</th>
                  <th scope="col" className="px-4 py-3 text-right">Bid</th>
                  <th scope="col" className="px-4 py-3 text-right">Ask</th>
                  <th scope="col" className="px-4 py-3 text-right">Spread</th>
                  <th scope="col" className="px-4 py-3 text-right">Volume</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredMarkets.map((market) => (
                  <tr
                    key={market.marketId}
                    onClick={() => handleSelect(market)}
                    className="hover:bg-bg-tertiary/60 cursor-pointer"
                  >
                    <td className="px-4 py-3 max-w-[320px]">
                      <div className="text-text-primary truncate">{market.question}</div>
                      <div className="text-xs text-text-secondary">
                        {market.conditionId ? market.conditionId.slice(0, 10) : 'No condition id'}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{market.category ?? '-'}</td>
                    <td className="px-4 py-3 text-right text-text-primary">
                      {market.bestBid !== null ? market.bestBid.toFixed(3) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-text-primary">
                      {market.bestAsk !== null ? market.bestAsk.toFixed(3) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-text-secondary">
                      {market.spread !== null ? market.spread.toFixed(3) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-text-primary">
                      {market.volume !== null ? `$${market.volume.toFixed(0)}` : '-'}
                    </td>
                  </tr>
                ))}
                {filteredMarkets.length === 0 && !isLoading && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-text-secondary">
                      No markets match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-bg-secondary rounded-2xl border border-border shadow-sm p-4 space-y-4">
          <div className="text-[11px] uppercase tracking-[0.3em] text-text-secondary/70">
            Market Detail
          </div>
          <h3 className="text-lg font-semibold text-text-primary">Selected Market</h3>
          {hasSelection ? (
            <div className="space-y-4 text-sm">
              <div>
                <div className="text-text-primary font-semibold">
                  {detail?.question ?? selectedMarket?.question ?? 'Unknown market'}
                </div>
                <div className="text-text-secondary text-xs">
                  {detail?.category ?? selectedMarket?.category ?? 'Uncategorized'}
                </div>
                <div className="text-text-secondary text-xs mt-1">
                  {detail?.endDate ? `Resolves ${detail.endDate}` : 'Resolution TBD'}
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Bid / Ask</span>
                  <span className="text-text-primary">
                    {bestBid !== null ? bestBid.toFixed(3) : '-'} / {bestAsk !== null ? bestAsk.toFixed(3) : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Mid</span>
                  <span className="text-text-primary">
                    {detail?.midPrice !== null && detail?.midPrice !== undefined
                      ? detail.midPrice.toFixed(3)
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Spread</span>
                  <span className="text-text-primary">
                    {detail?.spread !== null && detail?.spread !== undefined
                      ? detail.spread.toFixed(3)
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Liquidity</span>
                  <span className="text-text-primary">
                    {detail?.liquidity !== null && detail?.liquidity !== undefined
                      ? `$${detail.liquidity.toFixed(0)}`
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Volume</span>
                  <span className="text-text-primary">
                    {detail?.volume !== null && detail?.volume !== undefined
                      ? `$${detail.volume.toFixed(0)}`
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Updated</span>
                  <span className="text-text-primary">
                    {detail?.updatedAt || selectedMarket?.updatedAt
                      ? formatDistanceToNowStrict(new Date(detail?.updatedAt ?? selectedMarket?.updatedAt ?? '')) + ' ago'
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Time to End</span>
                  <span className="text-text-primary">
                    {detail?.timeToEndHours !== null && detail?.timeToEndHours !== undefined
                      ? `${detail.timeToEndHours.toFixed(1)}h`
                      : '-'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Filter Rejections</span>
                  <span className="text-text-primary">
                    {detail?.filterRejections !== null && detail?.filterRejections !== undefined
                      ? detail.filterRejections
                      : '-'}
                  </span>
                </div>
              </div>

              <div className="border-t border-border pt-3 space-y-2">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Token</div>
                {tokens.length > 0 ? (
                  <select
                    value={selectedTokenId ?? ''}
                    onChange={(event) => setSelectedTokenId(event.target.value)}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue"
                  >
                    {tokens.map((token) => (
                      <option key={token.tokenId} value={token.tokenId}>
                        {token.outcome ?? token.tokenId.slice(0, 6)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="text-xs text-accent-red bg-accent-red/10 border border-accent-red/30 rounded-lg p-2">
                    Token data unavailable. Backend may need restart or market data not yet loaded.
                  </div>
                )}
              </div>

              <div className="border-t border-border pt-3 space-y-2">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">
                  Signal Context
                </div>
                {lastSignal ? (
                  <div className="space-y-1 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Decision</span>
                      <span className="text-text-primary uppercase">{lastSignal.decision}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Model Score</span>
                      <span className="text-text-primary">
                        {lastSignal.modelScore !== null ? lastSignal.modelScore.toFixed(3) : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Trigger</span>
                      <span className="text-text-primary">
                        {lastSignal.price ? lastSignal.price.toFixed(3) : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Created</span>
                      <span className="text-text-primary">
                        {lastSignal.createdAt ? formatDistanceToNowStrict(new Date(lastSignal.createdAt)) + ' ago' : '-'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-text-secondary">No signal recorded yet.</div>
                )}
              </div>

              <div className="border-t border-border pt-3 space-y-2">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">
                  Orderbook
                </div>
                {orderbook && orderbook.source === 'snapshot' ? (
                  <div className="space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-bg-tertiary rounded-lg p-2">
                        <div className="text-text-secondary">Depth Bid (1/5/10%)</div>
                        <div className="text-text-primary mt-1">
                          {orderbook.depth.bid.pct1.toFixed(2)} / {orderbook.depth.bid.pct5.toFixed(2)} / {orderbook.depth.bid.pct10.toFixed(2)}
                        </div>
                      </div>
                      <div className="bg-bg-tertiary rounded-lg p-2">
                        <div className="text-text-secondary">Depth Ask (1/5/10%)</div>
                        <div className="text-text-primary mt-1">
                          {orderbook.depth.ask.pct1.toFixed(2)} / {orderbook.depth.ask.pct5.toFixed(2)} / {orderbook.depth.ask.pct10.toFixed(2)}
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-text-secondary mb-1">Top Bids</div>
                        <div className="space-y-1">
                          {orderbook.bids.slice(0, 4).map((level, idx) => (
                            <div key={`bid-${idx}`} className="flex items-center justify-between">
                              <span className="text-text-primary">{level.price.toFixed(3)}</span>
                              <span className="text-text-secondary">{level.size.toFixed(2)}</span>
                            </div>
                          ))}
                          {orderbook.bids.length === 0 && (
                            <div className="text-text-secondary">No bids.</div>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="text-text-secondary mb-1">Top Asks</div>
                        <div className="space-y-1">
                          {orderbook.asks.slice(0, 4).map((level, idx) => (
                            <div key={`ask-${idx}`} className="flex items-center justify-between">
                              <span className="text-text-primary">{level.price.toFixed(3)}</span>
                              <span className="text-text-secondary">{level.size.toFixed(2)}</span>
                            </div>
                          ))}
                          {orderbook.asks.length === 0 && (
                            <div className="text-text-secondary">No asks.</div>
                          )}
                        </div>
                      </div>
                    </div>
                    <div>
                      <div className="text-text-secondary mb-1">Slippage Estimate (bps)</div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="bg-bg-tertiary rounded-lg p-2">
                          <div className="text-text-secondary text-[10px] uppercase">Buy</div>
                          {orderbook.slippage.buy.map((row) => (
                            <div key={`buy-${row.size}`} className="flex items-center justify-between">
                              <span className="text-text-primary">{row.size.toFixed(2)}</span>
                              <span className="text-text-secondary">
                                {row.slippageBps !== null ? row.slippageBps.toFixed(1) : '--'}
                              </span>
                            </div>
                          ))}
                        </div>
                        <div className="bg-bg-tertiary rounded-lg p-2">
                          <div className="text-text-secondary text-[10px] uppercase">Sell</div>
                          {orderbook.slippage.sell.map((row) => (
                            <div key={`sell-${row.size}`} className="flex items-center justify-between">
                              <span className="text-text-primary">{row.size.toFixed(2)}</span>
                              <span className="text-text-secondary">
                                {row.slippageBps !== null ? row.slippageBps.toFixed(1) : '--'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-text-secondary">Orderbook snapshot unavailable.</div>
                )}
              </div>

              <div className="border-t border-border pt-3 space-y-3">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">
                  Manual Order
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <button
                    onClick={() => setOrderSide('BUY')}
                    className={`px-3 py-1 rounded-full border ${orderSide === 'BUY' ? 'border-accent-green text-accent-green' : 'border-border text-text-secondary'}`}
                  >
                    Buy
                  </button>
                  <button
                    onClick={() => setOrderSide('SELL')}
                    className={`px-3 py-1 rounded-full border ${orderSide === 'SELL' ? 'border-accent-red text-accent-red' : 'border-border text-text-secondary'}`}
                  >
                    Sell
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <label className="text-xs text-text-secondary">Limit Price</label>
                    <input
                      type="number"
                      step="0.001"
                      value={orderPrice}
                      onChange={(event) => setOrderPrice(event.target.value)}
                      className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
                      placeholder="0.85"
                    />
                    <div className="flex flex-wrap gap-2 text-[10px]">
                      <button
                        onClick={() => bestBid !== null && setOrderPrice(bestBid.toFixed(3))}
                        disabled={bestBid === null}
                        className="px-2 py-1 rounded-full border border-border text-text-secondary disabled:opacity-50"
                      >
                        Best Bid
                      </button>
                      <button
                        onClick={() => bestAsk !== null && setOrderPrice(bestAsk.toFixed(3))}
                        disabled={bestAsk === null}
                        className="px-2 py-1 rounded-full border border-border text-text-secondary disabled:opacity-50"
                      >
                        Best Ask
                      </button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs text-text-secondary">Size</label>
                    <input
                      type="number"
                      step="0.01"
                      value={orderSize}
                      onChange={(event) => setOrderSize(event.target.value)}
                      className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
                      placeholder="10"
                    />
                    <div className="flex flex-wrap gap-2 text-[10px]">
                      {sizePresets.map((preset) => (
                        <button
                          key={preset}
                          onClick={() => setOrderSize(preset.toFixed(2))}
                          className="px-2 py-1 rounded-full border border-border text-text-secondary"
                        >
                          {preset.toFixed(2)}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Reason</label>
                  <input
                    type="text"
                    value={orderReason}
                    onChange={(event) => setOrderReason(event.target.value)}
                    className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
                    placeholder="manual_override"
                  />
                </div>
                {orderError && <div className="text-xs text-accent-red">{orderError}</div>}
                {orderSuccess && <div className="text-xs text-accent-green">{orderSuccess}</div>}
                <button
                  onClick={handleManualOrder}
                  disabled={orderSubmitting || !selectedTokenId}
                  className="w-full rounded-full bg-accent-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-60"
                  title={!selectedTokenId ? 'Select a token first' : undefined}
                >
                  {orderSubmitting ? 'Submitting...' : !selectedTokenId ? 'Token Required' : 'Submit Manual Order'}
                </button>
              </div>

              {position && (
                <div className="border-t border-border pt-3 space-y-2">
                  <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Position</div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary">Size</span>
                    <span className="text-text-primary">{position.size.toFixed(2)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary">Entry</span>
                    <span className="text-text-primary">{position.entryPrice.toFixed(3)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary">Current</span>
                    <span className="text-text-primary">
                      {position.currentPrice !== null ? position.currentPrice.toFixed(3) : '-'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary">Unrealized</span>
                    <span className="text-text-primary">
                      {position.unrealizedPnl !== null ? `$${position.unrealizedPnl.toFixed(2)}` : '-'}
                    </span>
                  </div>
                </div>
              )}

              {openOrders.length > 0 && (
                <div className="border-t border-border pt-3 space-y-2">
                  <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Open Orders</div>
                  {openOrders.map((order) => (
                    <div key={order.orderId} className="flex items-center justify-between text-xs">
                      <span className="text-text-secondary">{order.side ?? '-'}</span>
                      <span className="text-text-primary">{order.price.toFixed(3)}</span>
                      <span className="text-text-secondary">{order.size.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="border-t border-border pt-3 space-y-2">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70">Execution</div>
                {lastFill ? (
                  <div className="space-y-1 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Last Fill</span>
                      <span className="text-text-primary">
                        {lastFill.price.toFixed(3)} x {lastFill.filledSize.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">Slippage (bps)</span>
                      <span className="text-text-primary">
                        {lastFill.slippageBps !== null ? lastFill.slippageBps.toFixed(1) : '--'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-text-secondary">No fills recorded.</div>
                )}
              </div>

              <div className="border-t border-border pt-3">
                <div className="text-xs uppercase tracking-[0.3em] text-text-secondary/70 mb-2">Recent Trades</div>
                {priceSeries.length > 1 && (
                  <div className="h-24 mb-3">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={priceSeries}>
                        <XAxis dataKey="timestamp" hide />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#0f141a', border: '1px solid #2a2f36', borderRadius: '8px' }}
                          formatter={(value: number) => [`${value.toFixed(3)}`, 'Price']}
                          labelFormatter={(label) => new Date(label).toLocaleTimeString()}
                        />
                        <Line
                          type="monotone"
                          dataKey="price"
                          stroke="#60a5fa"
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
                {marketHistory && marketHistory.length > 0 ? (
                  <div className="space-y-2">
                    {marketHistory.slice(0, 5).map((trade) => (
                      <div key={trade.tradeId} className="flex items-center justify-between text-xs">
                        <span className="text-text-secondary">{trade.side ?? '-'}</span>
                        <span className="text-text-primary">{trade.price?.toFixed(3) ?? '-'}</span>
                        <span className="text-text-secondary">{trade.size?.toFixed(2) ?? '-'}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-text-secondary">No recent trades.</div>
                )}
                {lastTrade && (
                  <div className="text-[10px] text-text-secondary mt-2">
                    Last trade {lastTrade.timestamp ? formatDistanceToNowStrict(new Date(lastTrade.timestamp)) + ' ago' : ''}
                  </div>
                )}
              </div>

              <div className="pt-3 border-t border-border flex flex-col gap-2">
                <button
                  onClick={() => effectiveConditionId && blockMarket(effectiveConditionId, 'operator_block', selectedTokenId ?? undefined)}
                  disabled={!effectiveConditionId}
                  className="w-full rounded-full border border-border px-4 py-2 text-xs font-semibold hover:border-accent-red hover:text-accent-red transition-colors disabled:opacity-50"
                >
                  Block Market
                </button>
                <button
                  onClick={() => effectiveConditionId && unblockMarket(effectiveConditionId)}
                  disabled={!effectiveConditionId}
                  className="w-full rounded-full border border-border px-4 py-2 text-xs font-semibold hover:border-accent-blue hover:text-accent-blue transition-colors disabled:opacity-50"
                >
                  Unblock Market
                </button>
              </div>
            </div>
          ) : (
            <div className="text-text-secondary text-sm">
              Select a market to see pricing, liquidity, and execution controls.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
