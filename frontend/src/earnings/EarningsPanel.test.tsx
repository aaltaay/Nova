/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EarningsPanel } from './EarningsPanel';
import type { EarningsView } from '../types/earnings';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function viewFor(range: EarningsView['range']): EarningsView {
  return {
    rev: '4',
    range,
    as_of: 1_735_689_600,
    error: null,
    days: [
      {
        date: '2026-09-01',
        label: 'Today · Tue Sep 1',
        count: 1,
        bmo: [],
        amc: [
          {
            symbol: 'NVDA',
            date: '2026-09-01',
            session: 'amc',
            eps_estimate: 1.12,
            eps_actual: null,
            revenue_estimate: null,
            revenue_actual: null,
            quarter: 3,
            year: 2026,
            company_name: 'NVIDIA',
            sector: 'Technology',
            market_cap: 3_100_000_000_000,
            logo_url: null,
          },
        ],
        intraday: [],
      },
    ],
  };
}

describe('EarningsPanel', () => {
  it('fetches the default "today" range and renders a day band', async () => {
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => viewFor('today'),
      status: 200,
      _url: url,
    }));
    vi.stubGlobal('fetch', fetchMock);

    let rendered: ReturnType<typeof render>;
    await act(async () => {
      rendered = render(
        <EarningsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/earnings?range=today'),
      expect.anything(),
    );
    expect(screen.getByText('NVIDIA')).toBeTruthy();
    expect(screen.getByText('Today · Tue Sep 1')).toBeTruthy();
    expect(rendered!.container.querySelector('.earnings-panel__count')?.textContent).toBe(
      '1 reports',
    );
  });

  it('clicking a range chip refetches with the new range', async () => {
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => viewFor(url.includes('range=week') ? 'week' : 'today'),
      status: 200,
    }));
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      render(
        <EarningsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('This week'));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/earnings?range=week'),
      expect.anything(),
    );
  });

  it('shows a loud error instead of pretending an empty list is fine', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        rev: '4',
        range: 'today',
        as_of: 0,
        error: 'FINNHUB_API_KEY is not set -- Earnings calendar has no data source.',
        days: [],
      }),
      status: 200,
    }));
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      render(
        <EarningsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText(/FINNHUB_API_KEY/)).toBeTruthy();
  });
});
