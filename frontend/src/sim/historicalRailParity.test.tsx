/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeDetail } from '../modules/quoteFixtures';
import { StockViewDepthTape } from '../stock_view/StockViewDepthTape';
import { captureQuoteDetail, historicalQuoteDetail } from './historicalQuoteDetail';
import type { SimClockState } from './simClockTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const hooks = vi.hoisted(() => ({
  snapshot: null as HistoricalSnapshot | null,
  tape: vi.fn(),
  visible: { level2: true, tape: true },
  depth: vi.fn(),
}));

vi.mock('./useHistoricalSnapshot', () => ({ useHistoricalSnapshot: () => hooks.snapshot }));
// Replay must never open the live feeds for a past session.
vi.mock('../ibkr/useIbkrTape', () => ({ useIbkrTape: hooks.tape }));
vi.mock('../ibkr/useIbkrDepth', () => ({ useIbkrDepth: hooks.depth }));
vi.mock('../workspace', async () => {
  const actual = await vi.importActual<typeof import('../workspace')>('../workspace');
  return {
    ...actual,
    useWorkspace: () => ({ ibkrConnected: false, discoveryProvider: 'ibkr' }),
    useModuleVisibility: () => ({ isVisible: (key: 'level2' | 'tape') => hooks.visible[key], setVisible: () => {}, visibility: {} }),
  };
});

function replaySnapshot(overrides: Partial<HistoricalSnapshot> = {}): HistoricalSnapshot {
  return {
    active: true, symbol: 'SPY', source: 'trades', as_of: '2026-09-18T04:41:16-04:00',
    last: 763, volume: 47784, open: 762.5, high: 763.2, low: 762.4, prev_close: 760,
    prints: [
      { time: '2026-09-18T08:41:00+00:00', price: 763.07, size: 1, exchange: 'FINRA', unreported: true },
      { time: '2026-09-18T08:39:25+00:00', price: 763, size: 500, exchange: 'ARCA', unreported: false },
      { time: '2026-09-18T08:39:12+00:00', price: 762.98, size: 100, exchange: 'NASDAQ', unreported: false },
    ],
    ...overrides,
  };
}

describe('historical replay keeps the live Stock Quote structure', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    hooks.visible = { level2: true, tape: true };
    hooks.tape.mockReset();
    hooks.depth.mockReset();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    hooks.snapshot = null;
  });

  async function render(snapshot: HistoricalSnapshot) {
    hooks.snapshot = snapshot;
    // Live detail is today's quote, halt and borrow state: none of it may reach replay.
    const live = makeDetail({
      symbol: 'SPY',
      halt: { halted: true, kind: 'luld', halt_code: 2, halt_start: 1_700_000_000, source: 'ibkr_ticker_halted' },
    });
    const todayBorrow = { state: 'shortable_est', shortable_shares: 123456, stale: false } as never;
    await act(async () => {
      root.render(<StockViewDepthTape selectedSymbol="SPY" detail={live} listingIbkr={todayBorrow} />);
    });
  }

  it('renders quote head, Level 2 frame and Time & Sales side by side', async () => {
    await render(replaySnapshot());
    expect(container.querySelector('[data-testid="stock-view-depth-side-by-side"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-l2-col"] [data-testid="historical-l2"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-l2-col"] .das-l2-colhead')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-tape-col"] [data-testid="ts-panel"]')).toBeTruthy();
    expect(container.querySelector('.sv-quote-card__last')?.textContent).toBe('$763.00');
    expect(container.querySelector('.sv-quote-card__chg')?.textContent).toBe('+3.00 (+0.39%)');
    expect(hooks.tape).not.toHaveBeenCalled();
    expect(hooks.depth).not.toHaveBeenCalled();
  });

  it("replaces today's halt and borrow chips with a visible replay note", async () => {
    await render(replaySnapshot());
    const head = container.querySelector('[data-testid="stock-view-l2-col"] .sv-md-pane__head')!;
    expect(head.querySelector('[data-testid="shortability-chip"]')).toBeNull();
    expect(head.querySelector('[data-testid="halt-eta-chip"]')).toBeNull();
    expect(head.querySelector('[data-testid="historical-l2-chip"]')?.textContent).toBe('ReplayNo L2 recorded');
    // The rail hides .ibkr-depth-fallback-badge, so the note must not depend on it.
    expect(container.querySelector('[data-testid="historical-l2"] .ibkr-depth-fallback-badge')).toBeNull();
    expect(container.querySelector('[data-testid="historical-l2-empty"]')).toBeTruthy();
  });

  it('shows the recorded book in the same Level 2 pane when the snapshot carries one', async () => {
    // Depth recorded locally for the replayed session (#309); the download
    // itself still has no book, which is why this arrives on the snapshot.
    await render(replaySnapshot({
      depth_available: true,
      depth: {
        symbol: 'SPY', bids: [{ price: 762.9, size: 200, side: 'bid', mm: 'ISLAND' }],
        asks: [{ price: 763.1, size: 300, side: 'ask', mm: 'ARCA' }],
        ts: 1_758_184_876, age_sec: 0.4, l1_fallback: false, source: 'l2_recorder',
      },
    }));
    const l2 = container.querySelector('[data-testid="stock-view-l2-col"]')!;
    expect(l2.querySelector('[data-testid="historical-l2-empty"]')).toBeNull();
    expect(l2.querySelector('[data-testid="historical-l2"]')?.getAttribute('data-depth-source'))
      .toBe('l2_recorder');
    expect(l2.querySelector('.das-l2-side--bid .das-l2-row--tiered .das-l2-price')?.textContent)
      .toBe('762.90');
    expect(l2.querySelector('[data-testid="historical-l2-chip"]')?.textContent).toBe('ReplayRecorded L2');
    // Still never the live feed for a past session.
    expect(hooks.depth).not.toHaveBeenCalled();
  });

  it.each([[false, true], [true, false], [false, false]])(
    'honors module visibility with level2=%s and tape=%s', async (level2, tape) => {
      hooks.visible = { level2, tape };
      await render(replaySnapshot());
      expect(Boolean(container.querySelector('[data-testid="stock-view-l2-col"]'))).toBe(level2);
      expect(Boolean(container.querySelector('[data-testid="stock-view-tape-col"]'))).toBe(tape);
      expect(container.querySelector('[data-testid="stock-view-depth-stack"]')).toBeTruthy();
      expect(container.querySelector('.sv-quote-card__last')?.textContent).toBe('$763.00');
      expect(hooks.tape).not.toHaveBeenCalled();
      expect(hooks.depth).not.toHaveBeenCalled();
    },
  );

  it('uses the live tape rows, REPLAY badge and dims unreported prints', async () => {
    await render(replaySnapshot());
    expect(container.querySelector('[data-testid="ts-status"]')?.textContent).toBe('REPLAY');
    expect(container.querySelector('[data-testid="ts-panel-cols"]')?.textContent).toBe('TimePriceSizeExch');
    const rows = [...container.querySelectorAll('.ts-row')];
    expect(rows.map(r => r.querySelector('.ts-col--exch')?.textContent)).toEqual(['FINRA', 'ARCA', 'NASDAQ']);
    expect(rows.map(r => r.classList.contains('ts-row--unreported'))).toEqual([true, false, false]);
    expect(rows[0].getAttribute('title')).toMatch(/Unreported/);
  });

  it('explains an empty tape when only candles were downloaded', async () => {
    await render(replaySnapshot({ source: 'completed_bars', prints: [] }));
    expect(container.querySelector('.ts-panel__empty')?.textContent).toMatch(/download trades/);
  });
});

describe('historicalQuoteDetail', () => {
  it('shows replay prices only, keeping fundamentals of the same ticker', () => {
    const live = makeDetail({ symbol: 'SPY', rel_volume: 3.2 });
    const out = historicalQuoteDetail(live, replaySnapshot({ session_open: 762.1, stats_scope: 'session' }));
    expect(out.snapshot.latest_trade?.price).toBe(763);
    // Gap% reads the session's open, never the window's first print (QA W7).
    expect(out.snapshot.daily_bar).toMatchObject({ open: 762.1, high: 763.2, low: 762.4, volume: 47784 });
    expect(out.snapshot.prev_close).toBe(760);
    expect(out.snapshot.latest_quote).toBeNull();
    expect(out.rel_volume).toBeNull();
    expect(out.halt).toBeNull();
    expect(out.listing).toBeNull();
    expect(out.fundamentals).toBe(live.fundamentals);
  });

  it('drops another ticker\'s fundamentals', () => {
    const out = historicalQuoteDetail(makeDetail({ symbol: 'AAPL' }), replaySnapshot());
    expect(out.symbol).toBe('SPY');
    expect(out.fundamentals).toBeNull();
  });

  it('a midday window states the session figures it cannot know instead of passing its own off (QA W7)', () => {
    // GRML Sep 21, window 13:00-13:30: open 9.22 is the window's first print; 09:30 was not downloaded.
    const out = historicalQuoteDetail(
      makeDetail({ symbol: 'GRML' }),
      replaySnapshot({ symbol: 'GRML', open: 9.22, high: 9.63, low: 9.02, volume: 812_340, prev_close: 2.85,
        session_open: null, stats_scope: 'window' }),
    );
    expect(out.snapshot.daily_bar).toMatchObject({ open: null, high: null, low: null, volume: null });
    expect(out.snapshot.prev_close).toBe(2.85);
    // With the stored 09:30 bar the gap is the session's +156.49%, not +223.51%.
    const known = historicalQuoteDetail(
      makeDetail({ symbol: 'GRML' }),
      replaySnapshot({ symbol: 'GRML', open: 9.22, prev_close: 2.85, session_open: 7.31, stats_scope: 'window' }),
    );
    const open = known.snapshot.daily_bar?.open ?? 0;
    expect(((open - 2.85) / 2.85) * 100).toBeCloseTo(156.49, 2);
  });
});

describe('captureQuoteDetail (QA W8)', () => {
  const clock = (quote: SimClockState['replay_quote']): SimClockState => ({
    sim: true, live_edge: false, replay_source: 'capture', replay_symbol: 'GRML', replay_quote: quote,
  });

  it('never carries the live ticker\'s volume, high, low or open into a recording replay', () => {
    const live = makeDetail({ symbol: 'GRML', rel_volume: 12 });
    live.snapshot.daily_bar = { open: 10.2, high: 10.9, low: 9.8, close: 10.46, volume: 3_502_196, trade_count: null, vwap: null, timestamp: null };
    const out = captureQuoteDetail(live, clock({
      symbol: 'GRML', ts: 1_790_010_000, covered: true, last: 8.84, bid: 8.82, ask: 8.85, bid_size: 100, ask_size: 200, prev_close: 2.85,
    }), 'GRML');
    expect(out.snapshot.daily_bar).toBeNull();
    expect(out.rel_volume).toBeNull();
    expect(out.snapshot.latest_trade?.price).toBe(8.84);
    expect(out.snapshot.latest_quote).toMatchObject({ bid_price: 8.82, ask_price: 8.85 });
    expect(out.snapshot.prev_close).toBe(2.85);
  });

  it('inside a recording gap there is no price either', () => {
    const out = captureQuoteDetail(makeDetail({ symbol: 'GRML' }), clock({
      symbol: 'GRML', ts: null, covered: false, last: null, bid: null, ask: null, bid_size: null, ask_size: null, prev_close: 2.85,
    }), 'GRML');
    expect(out.snapshot.latest_trade).toBeNull();
    expect(out.snapshot.latest_quote).toBeNull();
    expect(out.snapshot.daily_bar).toBeNull();
  });
});
