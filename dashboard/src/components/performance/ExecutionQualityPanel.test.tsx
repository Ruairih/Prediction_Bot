/**
 * Unit Tests for ExecutionQualityPanel Component
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ExecutionQualityPanel } from './ExecutionQualityPanel';
import type { Order } from '../../types';

const baseOrder: Order = {
  orderId: 'ord_1',
  tokenId: 'tok_1',
  conditionId: 'cond_1',
  question: 'Test order',
  side: 'BUY',
  price: 0.95,
  size: 10,
  filledSize: 10,
  status: 'filled',
  createdAt: '2024-01-01T00:00:00.000Z',
  updatedAt: '2024-01-01T00:00:02.000Z',
  slippage: undefined,
};

describe('ExecutionQualityPanel', () => {
  it('renders empty state when no orders are provided', () => {
    render(<ExecutionQualityPanel orders={[]} />);

    expect(screen.getByText(/no execution data/i)).toBeInTheDocument();
  });

  it('renders execution metrics for recent orders', () => {
    const orders: Order[] = [
      { ...baseOrder, orderId: 'ord_1', updatedAt: '2024-01-01T00:00:03.000Z' },
      { ...baseOrder, orderId: 'ord_2', status: 'filled', updatedAt: '2024-01-01T00:00:01.000Z' },
      { ...baseOrder, orderId: 'ord_3', status: 'cancelled', filledSize: 0 },
    ];

    render(<ExecutionQualityPanel orders={orders} />);

    expect(screen.getByText(/execution quality/i)).toBeInTheDocument();
    expect(screen.getByText(/^fill rate$/i)).toBeInTheDocument();
    expect(screen.getAllByText('66.7%')).toHaveLength(2);
    expect(screen.getByText(/^cancel rate$/i)).toBeInTheDocument();
    expect(screen.getByText('33.3%')).toBeInTheDocument();
    expect(screen.getByText(/avg slippage/i)).toBeInTheDocument();
    expect(screen.getAllByText(/n\/a/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/fill speed/i)).toBeInTheDocument();
    expect(screen.getByText('2.0s')).toBeInTheDocument();
  });
});
