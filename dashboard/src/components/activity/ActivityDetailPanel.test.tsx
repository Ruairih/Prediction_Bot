/**
 * Unit Tests for ActivityDetailPanel Component
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ActivityDetailPanel } from './ActivityDetailPanel';
import type { ActivityEvent } from '../../types';

describe('ActivityDetailPanel', () => {
  it('renders highlights for signal events', () => {
    const event: ActivityEvent = {
      id: 'evt_1',
      type: 'signal',
      timestamp: '2024-01-01T00:00:00.000Z',
      summary: 'Trigger: Test market',
      severity: 'info',
      details: {
        token_id: 'tok_123',
        condition_id: 'cond_456',
        price: 0.96,
        trade_size: 50,
        model_score: 0.97,
      },
    };

    render(
      <MemoryRouter>
        <ActivityDetailPanel event={event} onClose={() => undefined} />
      </MemoryRouter>
    );

    expect(screen.getByText(/event details/i)).toBeInTheDocument();
    expect(screen.getByText('Token')).toBeInTheDocument();
    expect(screen.getByText('tok_123')).toBeInTheDocument();
    expect(screen.getByText('Condition')).toBeInTheDocument();
    expect(screen.getByText('cond_456')).toBeInTheDocument();
    expect(screen.getByText(/model score/i)).toBeInTheDocument();
    expect(screen.getByText('97.0%')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view market details/i })).toBeInTheDocument();
  });
});
