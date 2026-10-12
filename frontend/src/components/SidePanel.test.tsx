/**
 * @vitest-environment jsdom
 *
 * The Scanner side panel's look-up (QA V36, operator decision 2026-09-22,
 * option a): it loads the Quote Panel in place, the global bar's search opens
 * the Trader, and the two must not read as the same door.
 *
 * On a Sim desk replaying one stock-day it is honest about any other symbol
 * (operator report 2026-10-12: SUNE picked off the Sep 9 board, LNKS loaded,
 * a dead chart and today's live $2.27 over the replay).
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
const shown = vi.hoisted(() => [] as Array<{ detail: { snapshot?: { latest_trade?: unknown } } }>);
vi.mock('./TickerDetailContent', () => ({
  TickerDetailContent: (props: { detail: { snapshot?: { latest_trade?: unknown } } }) => (shown.push(props), null),
}));
const simDesk = vi.hoisted(() => ({ sim: false, clock: null as unknown }));
const notices = vi.hoisted(() => [] as Array<{ symbol: string; select: (s: string) => void }>);
const simNotice = (symbol: string, select: (s: string) => void) => (notices.push({ symbol, select }), null);
vi.mock('../sim', async (importOriginal) => {
  const real = await importOriginal<typeof import('../sim')>();
  return {
    ...real,
    useSimReplayTarget: () => ({ sim: simDesk.sim, clock: simDesk.clock, target: { kind: 'ok' } }),
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
    // Float is not a session price: it stays.
    expect(detail.fundamentals).toEqual(sune.fundamentals);
  });

  it('shows the live quote untouched off Sim, with no notice', () => {
    workspace.selectedSymbol = 'SUNE';
    stream.detail = sune;
    render(<SidePanel simNotice={simNotice} />);

    expect(notices).toHaveLength(0);
    expect(shown.at(-1)?.detail).toBe(sune);
  });
});
