/**
 * Unit Tests for BotStatus Component
 *
 * Written FIRST (TDD) - defines expected behavior before implementation.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BotStatus } from './BotStatus';
import type { BotStatus as BotStatusType } from '../../types';

const mockStatus: BotStatusType = {
  mode: 'dry_run',
  status: 'healthy',
  lastHeartbeat: new Date().toISOString(),
  lastTradeTime: new Date().toISOString(),
  errorRate: 0,
  websocketConnected: true,
  version: '1.0.0',
};

describe('BotStatus', () => {
  it('displays current status', () => {
    render(<BotStatus status={mockStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText(/running/i)).toBeInTheDocument();
  });

  it('shows websocket connection status', () => {
    render(<BotStatus status={mockStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText(/connected/i)).toBeInTheDocument();
  });

  it('shows disconnected when websocket is down', () => {
    const disconnectedStatus = { ...mockStatus, websocketConnected: false };
    render(<BotStatus status={disconnectedStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText(/disconnected/i)).toBeInTheDocument();
  });

  it('displays last trade time in relative format', () => {
    render(<BotStatus status={mockStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    // Should show relative time like "2m ago" or "just now"
    expect(screen.getByText(/ago|just now/i)).toBeInTheDocument();
  });

  it('shows "No trades yet" when lastTradeTime is null', () => {
    const noTradesStatus = { ...mockStatus, lastTradeTime: null };
    render(<BotStatus status={noTradesStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText(/no trades/i)).toBeInTheDocument();
  });

  it('calls onPause when pause button clicked', () => {
    const onPause = vi.fn();
    render(<BotStatus status={mockStatus} onPause={onPause} onStop={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    expect(onPause).toHaveBeenCalled();
  });

  it('calls onStop when stop button clicked', () => {
    const onStop = vi.fn();
    render(<BotStatus status={mockStatus} onPause={vi.fn()} onStop={onStop} />);

    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    expect(onStop).toHaveBeenCalled();
  });

  it('shows error rate when non-zero', () => {
    const errorStatus = { ...mockStatus, errorRate: 0.05 };
    render(<BotStatus status={errorStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText(/5%/)).toBeInTheDocument();
  });

  it('applies warning styling when status is degraded', () => {
    const degradedStatus = { ...mockStatus, status: 'degraded' as const };
    render(<BotStatus status={degradedStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    const statusIndicator = screen.getByTestId('status-indicator');
    expect(statusIndicator).toHaveClass('bg-accent-yellow');
  });

  it('applies error styling when status is unhealthy', () => {
    const unhealthyStatus = { ...mockStatus, status: 'unhealthy' as const };
    render(<BotStatus status={unhealthyStatus} onPause={vi.fn()} onStop={vi.fn()} />);

    const statusIndicator = screen.getByTestId('status-indicator');
    expect(statusIndicator).toHaveClass('bg-accent-red');
  });
});
