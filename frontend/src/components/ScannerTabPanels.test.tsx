/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WatchlistEntry } from '../strategy/types';
import type { HealthStatus } from '../types/health';
import type { Gapper } from '../types/scanner';
import { ScannerTabPanels } from './ScannerTabPanels';

vi.mock('./useScannerRowFacts', () => ({
  useScannerRowFacts: () => ({ recording: false, allowlisted: false, depthHeld: false }),
}));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ symbols: [], isAllowed: () => false, add: vi.fn(), remove: vi.fn(), refresh: vi.fn() }),
}));

const AEHL: Gapper = {
  symbol: 'AEHL', price: 3.2, prev_close: 2.5, change_pct: 0.28, change_abs: 0.7, gap_percent: 0.28,
  volume: 1_000_000, rel_volume: null, has_news: false, newest_headline_at: null, market_cap: null,
  float: null, short_interest: null, short_ratio: null,
} as Gapper;

const TODAY: WatchlistEntry = {
  symbol: 'AEHL',
  composite_score: 2,
  sub_scores: { change_pct: 1, relative_volume: 0, float: 0, catalyst: 0 },
  five_pillars: { symbol: 'AEHL', all_pass: false, pass_count: 2, total: 5, checkmark: '2/5', pillars: [] },
};

describe('ScannerTabPanels WATCH column', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function render(historyDate: string | null) {
    await act(() => {
      root.render(
        <ScannerTabPanels
          activeTab="gappers"
          mode="premarket"
          health={{ status: 'connected', latency_ms: 1 } as HealthStatus}
          discoveryProvider="ibkr"
          gappers={[AEHL]}
          gainers={[]}
          losers={[]}
          afterhours={[]}
          largeCap={[]}
          catalysts={[]}
          watchlistEntries={[TODAY]}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
          pricesStale={false}
          flashSymbols={{}}
          historyDate={historyDate}
        />,
      );
    });
  }

  const watchCell = () => container.querySelector('td[data-col="watchlist_score"]') as HTMLElement | null;

  it("grades today's rows with today's watchlist", async () => {
    await render(null);
    expect(watchCell()?.textContent).toContain('2/5');
  });

  it("never puts today's score on a past snapshot's row (QA W14)", async () => {
    await render('2026-09-17');
    expect(watchCell()?.textContent).toBe('—');
  });
});
