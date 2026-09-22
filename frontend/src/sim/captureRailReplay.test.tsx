/**
 * A Session Record replaying in a Trader tab (QA 2026-09-22): the quote head
 * follows the playhead (R10), the tape says REPLAY and the Level 2 chip is the
 * recording's, not today's halt / borrow state (R16), and a gap in the
 * recording is stated, never shown as the market before it (R11).
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeDetail } from '../modules/quoteFixtures';
import { StockViewDepthTape } from '../stock_view/StockViewDepthTape';
import { simClockResource } from './simClockResource';

const hooks = vi.hoisted(() => ({
  fetch: vi.fn(),
  clock: {} as Record<string, unknown>,
}));

vi.mock('../api/novaFetch', () => ({ novaFetch: hooks.fetch }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: 'sim', connected: true }) }));
vi.mock('../ibkr/useIbkrTape', () => ({ useIbkrTape: () => ({ prints: [], connected: true, error: null }) }));
vi.mock('../ibkr/useIbkrDepth', () => ({
  useIbkrDepth: () => ({ book: null, connected: true, l1Fallback: false, error: null }),
}));
vi.mock('../workspace', async () => {
  const actual = await vi.importActual<typeof import('../workspace')>('../workspace');
  return {
    ...actual,
    useWorkspace: () => ({ ibkrConnected: true, discoveryProvider: 'ibkr', openStockView: () => {} }),
    useModuleVisibility: () => ({ isVisible: () => true, setVisible: () => {}, visibility: {} }),
  };
});

const QUOTE = { symbol: 'GRML', ts: 1, covered: true, last: 8.84, bid: 8.82, ask: 8.85, bid_size: 100, ask_size: 100, prev_close: 8.0 };
const CAPTURE = {
  sim: true, live_edge: false, scrubbed: true, replay_source: 'capture', replay_symbol: 'GRML', replay_date: '2026-09-21',
  replay_ok: true, sim_time_et: '2026-09-21T17:10:00-04:00', minute_max: 960,
  session_open_et: '2026-09-21T04:00:00-04:00', session_close_et: '2026-09-21T20:00:00-04:00',
  replay_load: { l2_total: 5, l2_loaded: 5, segments: [] }, replay_quote: QUOTE,
};

describe('a Session Record replaying in a Trader tab', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    hooks.fetch.mockReset();
    hooks.fetch.mockImplementation(async () => ({ ok: true, status: 200, json: async () => hooks.clock }));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function render(clock: Record<string, unknown>) {
    hooks.clock = clock;
    simClockResource.setData(null);
    // Today's live quote says 9.15; the replay at the playhead says 8.84.
    const live = makeDetail({ symbol: 'GRML' });
    await act(async () => {
      root.render(<StockViewDepthTape selectedSymbol="GRML" detail={live} />);
    });
    await act(async () => { await Promise.resolve(); });
  }

  it("prices the head from the replay at the playhead, and the panes are the recording's", async () => {
    await render(CAPTURE);
    expect(container.querySelector('.sv-quote-card__last')?.textContent).toBe('$8.84');
    expect(container.querySelector('.sv-quote-card__chg')?.textContent).toBe('+0.84 (+10.50%)');
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('REPLAY');
    expect(container.querySelector('[data-testid="capture-l2-chip"]')?.textContent).toBe('ReplayRecorded L2');
    expect(container.querySelector('[data-testid="shortability-chip"]')).toBeNull();
    expect(container.querySelector('[data-testid="halt-eta-chip"]')).toBeNull();
  });

  it('states a gap in the recording instead of showing the market before it', async () => {
    await render({ ...CAPTURE, replay_quote: { ...QUOTE, covered: false, last: null, bid: null, ask: null } });
    expect(container.querySelector('[data-testid="stock-view-quote-missing"]')?.getAttribute('title'))
      .toMatch(/Not recorded at this moment/);
    expect(container.querySelector('[data-testid="historical-l2-empty"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="capture-l2-chip"]')?.textContent).toBe('ReplayNo L2 recorded');
    expect(container.textContent).toMatch(/Not recorded at this moment -- a gap in the recording/);
  });
});
