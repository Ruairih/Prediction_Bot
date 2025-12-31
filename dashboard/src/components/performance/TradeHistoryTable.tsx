/**
 * Trade History Table Component
 */
import clsx from 'clsx';
import { format } from 'date-fns';
import { PnlBadge } from '../common/PnlBadge';
import type { Trade } from '../../types';

export interface TradeHistoryTableProps {
  trades: Trade[];
  onTradeClick: (trade: Trade) => void;
}

export function TradeHistoryTable({ trades, onTradeClick }: TradeHistoryTableProps) {
  return (
    <div
      data-testid="trade-history-table"
      className="bg-bg-secondary rounded-lg border border-border overflow-hidden"
    >
      <h3 className="text-lg font-semibold p-4 border-b border-border text-text-primary">
        Trade History
      </h3>
      {/* Horizontal scroll wrapper for mobile */}
      <div className="overflow-x-auto -webkit-overflow-scrolling-touch">
        <table className="w-full min-w-[700px]" aria-label="Trade history">
          <caption className="sr-only">
            Historical trades showing market, side, size, entry and exit prices, profit/loss, and date
          </caption>
          <thead className="bg-bg-tertiary">
            <tr>
              <th scope="col" className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                Market
              </th>
              <th scope="col" className="px-4 py-3 text-center text-sm font-medium text-text-secondary">
                Side
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Size
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Entry
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Exit
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                P&L
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-medium text-text-secondary">
                Date
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {trades.map((trade) => (
              <tr
                key={trade.tradeId}
                onClick={() => onTradeClick(trade)}
                className="hover:bg-bg-tertiary/50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="max-w-xs text-sm text-text-primary truncate">
                    {trade.question}
                  </div>
                </td>
                <td className="px-4 py-3 text-center">
                  <span
                    className={clsx(
                      'px-2 py-1 rounded text-xs font-medium',
                      trade.side === 'BUY'
                        ? 'bg-accent-green/20 text-accent-green'
                        : 'bg-accent-red/20 text-accent-red'
                    )}
                  >
                    {trade.side}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  {trade.size}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  ${trade.entryPrice.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-primary">
                  {trade.exitPrice ? `$${trade.exitPrice.toFixed(2)}` : '-'}
                </td>
                <td className="px-4 py-3 text-right">
                  <PnlBadge value={trade.pnl} />
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-secondary">
                  {format(new Date(trade.openedAt), 'MMM d, yyyy')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
