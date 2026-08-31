/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { EarningsLane } from './EarningsLane';
import { EARNINGS_LANE_PREVIEW_CAP } from '../constants';
import type { EarningsRow } from '../types/earnings';

afterEach(() => cleanup());

function rowFor(symbol: string): EarningsRow {
  return {
    symbol,
    date: '2026-09-01',
    session: 'bmo',
    eps_estimate: null,
    eps_actual: null,
    revenue_estimate: null,
    revenue_actual: null,
    quarter: null,
    year: null,
    company_name: null,
    sector: null,
    market_cap: null,
  };
}

describe('EarningsLane', () => {
  it('renders nothing for an empty lane', () => {
    const { container } = render(
      <EarningsLane label="Before open" rows={[]} selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
    );
    expect(container.textContent).toBe('');
  });

  it('truncates to the preview cap and expands on "+N more"', () => {
    const total = EARNINGS_LANE_PREVIEW_CAP + 3;
    const rows = Array.from({ length: total }, (_, i) => rowFor(`SYM${i}`));
    render(
      <EarningsLane label="Before open" rows={rows} selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
    );
    expect(screen.getAllByText(/^SYM/).length).toBe(EARNINGS_LANE_PREVIEW_CAP);
    fireEvent.click(screen.getByText('+3 more'));
    expect(screen.getAllByText(/^SYM/).length).toBe(total);
  });
});
