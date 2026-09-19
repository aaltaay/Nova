/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeDetail } from '../modules/quoteFixtures';
import { StockViewDepthTape } from '../stock_view/StockViewDepthTape';
import { historicalQuoteDetail } from './historicalQuoteDetail';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const hooks = vi.hoisted(() => ({
  snapshot: null as HistoricalSnapshot | null,
  tape: vi.fn(),
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
    useModuleVisibility: () => ({ isVisible: () => true, setVisible: () => {}, visibility: {} }),
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
  });

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
    const out = historicalQuoteDetail(live, replaySnapshot());
    expect(out.snapshot.latest_trade?.price).toBe(763);
    expect(out.snapshot.daily_bar).toMatchObject({ open: 762.5, high: 763.2, low: 762.4, volume: 47784 });
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
});
