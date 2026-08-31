/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EarningsCard } from './EarningsCard';
import type { EarningsRow } from '../types/earnings';

afterEach(() => cleanup());

const ROW: EarningsRow = {
  symbol: 'NVDA',
  date: '2026-09-01',
  session: 'amc',
  eps_estimate: 1.12,
  eps_actual: null,
  revenue_estimate: 54_200_000_000,
  revenue_actual: null,
  quarter: 3,
  year: 2026,
  company_name: 'NVIDIA',
  sector: 'Technology',
  market_cap: 3_100_000_000_000,
  logo_url: null,
};

describe('EarningsCard (ADR 011 row-vs-ticker split)', () => {
  it('clicking the card body only selects -- it does not open Trader', () => {
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();
    render(
      <EarningsCard row={ROW} selectedSymbol={null} onSelect={onSelect} onOpenTrading={onOpenTrading} />,
    );
    fireEvent.click(screen.getByText('NVIDIA'));
    expect(onSelect).toHaveBeenCalledWith('NVDA');
    expect(onOpenTrading).not.toHaveBeenCalled();
  });

  it('clicking the blue ticker button selects and opens Trader', () => {
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();
    render(
      <EarningsCard row={ROW} selectedSymbol={null} onSelect={onSelect} onOpenTrading={onOpenTrading} />,
    );
    fireEvent.click(screen.getByText('NVDA'));
    expect(onSelect).toHaveBeenCalledWith('NVDA');
    expect(onOpenTrading).toHaveBeenCalledWith('NVDA');
  });

  it('shows company name, sector/market cap, and EPS estimate', () => {
    render(<EarningsCard row={ROW} selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />);
    expect(screen.getByText('NVIDIA')).toBeTruthy();
    expect(screen.getByText(/Technology/)).toBeTruthy();
    expect(screen.getByText('$1.12')).toBeTruthy();
  });

  it('falls back to a dash when company name is unknown (cold fundamentals cache)', () => {
    render(
      <EarningsCard
        row={{ ...ROW, company_name: null, sector: null, market_cap: null }}
        selectedSymbol={null}
        onSelect={() => {}}
        onOpenTrading={() => {}}
      />,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('renders logo image when logo_url is present', () => {
    const { container } = render(
      <EarningsCard
        row={{ ...ROW, logo_url: 'https://static.example/nvda.png' }}
        selectedSymbol={null}
        onSelect={() => {}}
        onOpenTrading={() => {}}
      />,
    );
    const img = container.querySelector('img.earnings-card__logo') as HTMLImageElement | null;
    expect(img?.src).toContain('nvda.png');
  });

  it('shows letter fallback when logo_url is missing', () => {
    const { container } = render(
      <EarningsCard row={ROW} selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
    );
    expect(container.querySelector('.earnings-card__logo--fallback')?.textContent).toBe('N');
  });
});
