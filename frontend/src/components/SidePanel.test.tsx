/**
 * @vitest-environment jsdom
 *
 * The Scanner side panel's look-up (QA V36, operator decision 2026-09-22,
 * option a): it loads the Quote Panel in place, the global bar's search opens
 * the Trader, and the two must not read as the same door.
 *
 * On a Sim desk replaying one stock-day it is honest about any other symbol
 * (operator report 2026-10-12: SUNE picked off the Sep 9 board, LNKS loaded,
 * a dead chart and today's live $2.27 over the replay). The replay's own symbol
 * shows the replay's quote, today's company figures and Contenders rank are left
 * out, and the panel says so (operator report 2026-10-12: GRML on Jul 15 showed
 * today's $6.02, float and "#22 of the Contenders").
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GLOBAL_BAR_SEARCH_ARIA } from '../constantGroups/global_bar';
import {
  QUOTE_PANEL_COLLAPSE,
  QUOTE_PANEL_EXPAND,
  QUOTE_PANEL_LOOKUP_ARIA,
  QUOTE_PANEL_LOOKUP_PLACEHOLDER,
} from '../constantGroups/scanner_board';
import { SidePanel } from './SidePanel';

const { workspace } = vi.hoisted(() => ({
  workspace: {
    selectedSymbol: null as string | null,
    setSelectedSymbol: vi.fn(),
    openStockView: vi.fn(),
  },
}));

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));
const streamed = vi.hoisted(() => [] as Array<string | null>);
const stream = vi.hoisted(() => ({ detail: null as unknown }));
vi.mock('../hooks/useTickerStream', () => ({
  useTickerStream: (symbol: string | null) => (streamed.push(symbol), {
    detail: stream.detail,
    loading: false,
    refreshing: false,
    fetchFailed: false,
    stale: false,
    disconnectedSince: null,
  }),
}));
interface Shown {
  detail: { snapshot?: { latest_trade?: unknown } };
  watchlistEntry?: unknown;
  watchlistRank?: number | null;
  replayNote?: string | null;
}
const shown = vi.hoisted(() => [] as Shown[]);
vi.mock('./TickerDetailContent', () => ({
  TickerDetailContent: (props: Shown) => (shown.push(props), null),
}));
const simDesk = vi.hoisted(() => ({ sim: false, clock: null as unknown, snapshot: null as unknown }));
const notices = vi.hoisted(() => [] as Array<{ symbol: string; select: (s: string) => void }>);
const simNotice = (symbol: string, select: (s: string) => void) => (notices.push({ symbol, select }), null);
vi.mock('../sim', async (importOriginal) => {
  const real = await importOriginal<typeof import('../sim')>();
  return {
    ...real,
    useSimReplayTarget: () => ({ sim: simDesk.sim, clock: simDesk.clock, target: { kind: 'ok' } }),
    useHistoricalSnapshot: () => simDesk.snapshot,
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  streamed.length = 0;
  shown.length = 0;
  notices.length = 0;
  stream.detail = null;
  simDesk.sim = false;
  simDesk.clock = null;
  simDesk.snapshot = null;
  workspace.selectedSymbol = null;
});

describe('SidePanel look-up (QA V36)', () => {
  it('names itself as the Quote Panel door, not the header search', () => {
    render(<SidePanel />);

    expect(screen.getByRole('button', { name: 'Quote panel: look up' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Look Up' })).toBeNull();

    const input = screen.getByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA });
    expect(QUOTE_PANEL_LOOKUP_ARIA).toMatch(/quote panel on this page/i);
    expect(screen.queryByRole('textbox', { name: GLOBAL_BAR_SEARCH_ARIA })).toBeNull();
    expect(input.getAttribute('placeholder')).toBe(QUOTE_PANEL_LOOKUP_PLACEHOLDER);
  });

  it('still loads the symbol in place and never opens the Trader', () => {
    render(<SidePanel />);

    fireEvent.change(screen.getByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA }), {
      target: { value: ' aapl ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Quote panel: look up' }));

    expect(workspace.setSelectedSymbol).toHaveBeenCalledWith('AAPL');
    expect(workspace.openStockView).not.toHaveBeenCalled();
  });
});

describe('SidePanel collapse (operator ask, 2026-09-23)', () => {
  it('folds to a strip on the right that names the symbol, and unfolds from it', () => {
    workspace.selectedSymbol = 'WHLR';
    const onToggle = vi.fn();
    const { rerender } = render(<SidePanel collapsed={false} onToggleCollapsed={onToggle} />);
    expect(screen.getByTestId('quote-panel').getAttribute('data-collapsed')).toBe('0');
    fireEvent.click(screen.getByRole('button', { name: QUOTE_PANEL_COLLAPSE }));
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(<SidePanel collapsed onToggleCollapsed={onToggle} />);
    expect(screen.getByTestId('quote-panel').getAttribute('data-collapsed')).toBe('1');
    expect(screen.getByTestId('quote-panel-expand').textContent).toBe('Quote Panel · WHLR');
    expect(screen.queryByRole('textbox', { name: QUOTE_PANEL_LOOKUP_ARIA })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: QUOTE_PANEL_EXPAND }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('streams nothing while folded', () => {
    workspace.selectedSymbol = 'WHLR';
    render(<SidePanel collapsed onToggleCollapsed={() => {}} />);
    expect(streamed.every(sym => sym === null)).toBe(true);
    cleanup();
    render(<SidePanel collapsed={false} onToggleCollapsed={() => {}} />);
    expect(streamed.at(-1)).toBe('WHLR');
  });

  it('has no collapse control where the host gives it no toggle', () => {
    render(<SidePanel />);
    expect(screen.queryByTestId('quote-panel-collapse')).toBeNull();
  });
});

describe('SidePanel on a Sim replay (operator report, 2026-10-12)', () => {
  const sune = {
    symbol: 'SUNE',
    asset: { name: 'SUNation Energy' },
    fundamentals: { float_shares: 4653225 },
    snapshot: {
      latest_trade: { price: 2.27, timestamp: '2026-10-12T21:55:56Z' },
      daily_bar: { open: 2.3, high: 2.4, low: 2.2, close: 2.27, volume: 52005 },
      prev_close: 2.28,
    },
  };
  const lnksLoaded = {
    live_edge: false, replay_ok: true, replay_loading: false,
    replay_source: 'historical', replay_symbol: 'LNKS', session_date: '2026-09-09',
  };

  it('offers the way to load another symbol and keeps the live quote off the replay', () => {
    workspace.selectedSymbol = 'SUNE';
    stream.detail = sune;
    simDesk.sim = true;
    simDesk.clock = lnksLoaded;
    render(<SidePanel simNotice={simNotice} />);

    expect(notices.at(-1)?.symbol).toBe('SUNE');
    // "Go to LNKS" stays on the scanner: it selects the replay in this panel.
    notices.at(-1)?.select('LNKS');
    expect(workspace.setSelectedSymbol).toHaveBeenCalledWith('LNKS');
    expect(workspace.openStockView).not.toHaveBeenCalled();
    const detail = shown.at(-1)?.detail as typeof sune;
    expect(detail.snapshot.latest_trade).toBeNull();
    expect(detail.snapshot.daily_bar).toBeNull();
    // Today's float is not Sep 9's: left out, and the panel says so.
    expect(detail.fundamentals.float_shares).toBeNull();
    expect(shown.at(-1)?.replayNote).toMatch(/^Replay of Sep 9: float, short interest, market cap/);
  });

  it("shows the loaded replay's own quote at the playhead, not an empty one", () => {
    workspace.selectedSymbol = 'GRML';
    stream.detail = { ...sune, symbol: 'GRML', fundamentals: { float_shares: 3075412, sector: 'Basic Materials',
      recent_split: '1:50 (2026-08-24)' } };
    simDesk.sim = true;
    simDesk.clock = { ...lnksLoaded, replay_symbol: 'GRML', session_date: '2026-07-15' };
    simDesk.snapshot = {
      active: true, symbol: 'GRML', last: 0.1875, volume: 27524, source: 'massive', as_of: '2026-07-15T11:20:26Z',
      session_open: null, stats_scope: 'session', high: 0.19, low: 0.18, prev_close: 0.1801, covered: true,
    };
    render(<SidePanel simNotice={simNotice} />);

    const detail = shown.at(-1)?.detail as unknown as {
      snapshot: { latest_trade: { price: number }; prev_close: number };
      fundamentals: { float_shares: number | null; sector: string | null; recent_split: string | null };
    };
    expect(detail.snapshot.latest_trade.price).toBe(0.1875);
    expect(detail.snapshot.prev_close).toBe(0.1801);
    expect(detail.fundamentals).toMatchObject({ float_shares: null, sector: 'Basic Materials', recent_split: null });
    expect(shown.at(-1)?.replayNote).toBe(
      "Replay of Jul 15: float, short interest, market cap, the 52-week range and broker flags are not shown -- "
      + "Nova holds today's figures only, not that day's. GRML split 1:50 (2026-08-24), after this day.",
    );
  });

  it("never hands today's Contenders rank to the strip off the live edge", () => {
    const ranked = { symbol: 'GRML', composite_score: 19.2, sub_scores: {}, five_pillars: { pillars: [] } };
    workspace.selectedSymbol = 'GRML';
    stream.detail = { ...sune, symbol: 'GRML' };
    const entries = [ranked] as unknown as Parameters<typeof SidePanel>[0]['watchlistEntries'];
    simDesk.sim = true;
    simDesk.clock = { ...lnksLoaded, replay_symbol: 'GRML' };
    render(<SidePanel watchlistEntries={entries} simNotice={simNotice} />);
    expect(shown.at(-1)?.watchlistEntry).toBeNull();
    expect(shown.at(-1)?.watchlistRank).toBeNull();

    cleanup();
    simDesk.clock = { ...lnksLoaded, live_edge: true };
    render(<SidePanel watchlistEntries={entries} simNotice={simNotice} />);
    expect(shown.at(-1)?.watchlistEntry).toBe(ranked);
    expect(shown.at(-1)?.watchlistRank).toBe(1);
    expect(shown.at(-1)?.replayNote).toBeNull();
  });

  it('shows the live quote untouched off Sim, with no notice', () => {
    workspace.selectedSymbol = 'SUNE';
    stream.detail = sune;
    render(<SidePanel simNotice={simNotice} />);

    expect(notices).toHaveLength(0);
    expect(shown.at(-1)?.detail).toBe(sune);
    expect(shown.at(-1)?.replayNote).toBeNull();
  });
});
