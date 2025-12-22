/**
 * Unit Tests for KpiTile Component
 *
 * Written FIRST (TDD) - defines expected behavior before implementation.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { KpiTile } from './KpiTile';

describe('KpiTile', () => {
  it('renders label and value', () => {
    render(<KpiTile label="Total P&L" value="$47.82" testId="kpi-total-pnl" />);

    expect(screen.getByText('Total P&L')).toBeInTheDocument();
    expect(screen.getByText('$47.82')).toBeInTheDocument();
  });

  it('applies positive styling for positive trend', () => {
    render(<KpiTile label="P&L" value="$10" trend="up" testId="kpi-pnl" />);

    const value = screen.getByText('$10');
    expect(value).toHaveClass('text-accent-green');
  });

  it('applies negative styling for negative trend', () => {
    render(<KpiTile label="P&L" value="-$10" trend="down" testId="kpi-pnl" />);

    const value = screen.getByText('-$10');
    expect(value).toHaveClass('text-accent-red');
  });

  it('shows change indicator when provided', () => {
    render(
      <KpiTile
        label="Win Rate"
        value="98.5%"
        change="+2.1%"
        trend="up"
        testId="kpi-win-rate"
      />
    );

    // Use regex to match text that may be split by arrow indicator
    expect(screen.getByText(/\+2\.1%/)).toBeInTheDocument();
  });

  it('uses correct test ID for identification', () => {
    render(<KpiTile label="Test" value="123" testId="kpi-test" />);

    expect(screen.getByTestId('kpi-test')).toBeInTheDocument();
  });

  it('renders with neutral styling when no trend', () => {
    render(<KpiTile label="Positions" value="3" testId="kpi-positions" />);

    const value = screen.getByText('3');
    expect(value).not.toHaveClass('text-accent-green');
    expect(value).not.toHaveClass('text-accent-red');
  });
});
