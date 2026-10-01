import { describe, expect, it } from 'vitest';
import {
  compactAge,
  connectionChipView,
  type ConnectionChipInput,
} from './globalBarConnectionModel';

function input(overrides: Partial<ConnectionChipInput> = {}): ConnectionChipInput {
  return {
    sampleDataActive: false,
    apiOk: true,
    apiTitle: 'Nova API process is reachable on port 8000.',
    connected: true,
    statusStale: false,
    staleForSec: null,
    delayed: false,
    gatewayTitle: 'Gateway: live session on 4001.',
    pricesStale: false,
    secondsAgo: 6,
    lastPriceTs: 1_700_000_000,
    historyDate: null,
    honestyText: null,
    isIbkr: true,
    activeFeed: 'ibkr',
    feedFellBack: false,
    scannerModeLabel: 'Pre-Market',
    ...overrides,
  };
}

describe('connectionChipView', () => {
  it('says IBKR live in muted green when everything is fresh', () => {
    const view = connectionChipView(input());
    expect(view).toMatchObject({ tone: 'ok', state: 'live', label: 'IBKR live' });
    expect(view.title).toContain('Nova API process is reachable');
    expect(view.title).toContain('Gateway: live session on 4001.');
    expect(view.title).toContain('Prices: 6s ago');
    expect(view.title).toContain('Scanner mode: Pre-Market');
    expect(view.title).toMatch(/Click for the API and Gateway checklist/);
  });

  it('is amber SAMPLE DATA on the sample desk, and names it truthfully', () => {
    const view = connectionChipView(input({ sampleDataActive: true, connected: false }));
    expect(view).toMatchObject({ tone: 'warn', state: 'sample', label: 'SAMPLE DATA' });
    expect(view.title).toContain('Nova Marketing Sample Data');
    expect(view.title).not.toContain('port 8000');
  });

  it('is red API down before anything about the Gateway', () => {
    const view = connectionChipView(input({ apiOk: false, apiTitle: 'Nova API is unreachable -- start the backend (port 8000).' }));
    expect(view).toMatchObject({ tone: 'bad', state: 'api-down', label: 'API down' });
    expect(view.title).toContain('port 8000');
  });

  it('is red IBKR offline when the Gateway session is down', () => {
    const view = connectionChipView(input({ connected: false }));
    expect(view).toMatchObject({ tone: 'bad', state: 'offline', label: 'IBKR offline' });
  });

  it('is amber STALE with an age when the status poll or the scanner prices are late', () => {
    expect(connectionChipView(input({ statusStale: true, staleForSec: 42 }))).toMatchObject({
      tone: 'warn',
      state: 'stale',
      label: 'STALE 42s',
    });
    expect(connectionChipView(input({ statusStale: true, staleForSec: null })).label).toBe('STALE');
    const prices = connectionChipView(input({ pricesStale: true, secondsAgo: 125 }));
    expect(prices).toMatchObject({ tone: 'warn', state: 'stale', label: 'STALE 2m' });
    expect(prices.title).toContain('Prices: stale · 2m ago');
  });

  it('does not say STALE 0s for fresh prices behind an L1 subscription error', () => {
    // 2026-10-01: Error 101 (max tickers) set pricesStale with prices 0 s old all morning.
    const view = connectionChipView(input({
      pricesStale: true, secondsAgo: 0, honestyText: 'Error 101: Max number of tickers has been reached',
    }));
    expect(view).toMatchObject({ tone: 'ok', state: 'live', label: 'IBKR live' });
    expect(view.title).toContain('Prices: 0s ago');
    expect(view.title).toContain('Max number of tickers');
  });

  it('is red NO DATA while the IBKR feed is silent, and amber DATA GAP after (#672)', () => {
    const noData = connectionChipView(input({
      feedGap: { tone: 'bad', state: 'no-data', label: 'NO DATA 9s', title: 'No IBKR data on any line for 9 s.' },
      pricesStale: true, secondsAgo: 9,
    }));
    expect(noData).toMatchObject({ tone: 'bad', state: 'no-data', label: 'NO DATA 9s' });
    expect(noData.title.split('\n\n')[1]).toBe('No IBKR data on any line for 9 s.');
    const after = connectionChipView(input({
      feedGap: { tone: 'warn', state: 'data-gap', label: 'DATA GAP 16s', title: 'No IBKR data for 16 s.' },
    }));
    expect(after).toMatchObject({ tone: 'warn', state: 'data-gap', label: 'DATA GAP 16s' });
    // A disconnected Gateway is the header's own state; the gap does not hide it.
    expect(connectionChipView(input({
      connected: false,
      feedGap: { tone: 'bad', state: 'no-data', label: 'NO DATA 9s', title: 'x' },
    })).state).toBe('offline');
  });

  it('does not call history browsing stale', () => {
    const view = connectionChipView(input({ pricesStale: true, secondsAgo: 9999, historyDate: '2026-09-18' }));
    expect(view.label).toBe('IBKR live');
    expect(view.title).not.toContain('Prices:');
  });

  it('is amber IBKR delayed on delayed market data', () => {
    expect(connectionChipView(input({ delayed: true }))).toMatchObject({
      tone: 'warn',
      state: 'delayed',
      label: 'IBKR delayed',
    });
  });

  it('keeps no-L1-yet, the roster honesty text and the legacy feed wording in the tooltip', () => {
    const view = connectionChipView(
      input({ lastPriceTs: 0, secondsAgo: null, honestyText: 'last-good', isIbkr: false, activeFeed: 'iex', feedFellBack: true }),
    );
    expect(view.label).toBe('IBKR live');
    expect(view.title).toContain('Prices: no L1 yet');
    expect(view.title).toContain('Roster: last-good');
    expect(view.title).toContain('fell back to IEX');
  });
});

describe('compactAge', () => {
  it('keeps one number', () => {
    expect(compactAge(0)).toBe('0s');
    expect(compactAge(59.9)).toBe('59s');
    expect(compactAge(60)).toBe('1m');
    expect(compactAge(3_599)).toBe('59m');
    expect(compactAge(3_600)).toBe('1h');
    expect(compactAge(48 * 3_600)).toBe('2d');
  });
});
