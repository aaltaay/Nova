/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import { StockViewTabStrip } from './StockViewTabStrip';

const mocks = vi.hoisted(() => ({
  rows: null as ScannerDockRows | null,
  recording: [] as string[],
}));

vi.mock('../scanner/useScannerDockRows', () => ({
  useScannerDockRows: () => mocks.rows,
}));

vi.mock('../capture/sessionRecordStore', () => ({
  getRecordingSymbols: () => mocks.recording,
  isTabRecording: (symbol: string) => mocks.recording.includes(symbol.toUpperCase()),
  subscribeSessionRecord: () => () => {},
}));

/** Fixtures author the gap in percent; the wire carries a fraction (QA V2 / C17). */
const frac = (pct: number | null): number | null => (pct == null ? null : pct / 100);

function row(symbol: string, gap: number | null, hasNews = false): ScannerDockRows['gappers'][number] {
  return {
    symbol, price: 8.9, prev_close: 3.85, change_pct: frac(gap), change_abs: null, gap_percent: frac(gap), volume: 0,
    rel_volume: null, has_news: hasNews, newest_headline_at: null, market_cap: null, float: null,
    short_interest: null, short_ratio: null,
  };
}

function rows(overrides: Partial<ScannerDockRows> = {}): ScannerDockRows {
  return {
    gappers: [], gainers: [], losers: [], afterhours: [], catalysts: [], watchlistEntries: [],
    mode: 'market', health: { status: 'ok', latency_ms: 1 }, discoveryProvider: 'ibkr', pricesStale: false,
    flashSymbols: {}, rowQuoteTs: {}, nowSec: 0, tableMeta: {},
    counts: { gappers: 0, gainers: 0, losers: 0, afterhours: 0, catalysts: 0 }, setL1DockTab: null,
    ...overrides,
  };
}

describe('StockViewTabStrip', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.rows = null;
    mocks.recording = [];
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('extract icon and double-click pop the tab out -- + stays in this window, the drag hint is the tooltip', async () => {
    const onExtract = vi.fn();
    const onAddDraft = vi.fn();
    const onActivate = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['SPY', 'IPST']}
          active="SPY"
          onActivate={onActivate}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={onAddDraft}
          onExtract={onExtract}
        />,
      );
    });
    const label = container.querySelector('[data-testid="sv-tab-SPY"] .sv-tab__label') as HTMLButtonElement;
    expect(label.title).toMatch(/Double-click to pop out/i);
    const extract = container.querySelector('[data-testid="sv-tab-extract-SPY"]') as HTMLButtonElement;
    expect(extract).toBeTruthy();
    expect(extract.getAttribute('aria-label')).toMatch(/new window/i);
    expect(extract.textContent).toBe(''); // an icon, not the permanent POP OUT word
    await act(async () => {
      extract.click();
    });
    expect(onExtract).toHaveBeenCalledWith('SPY');
    await act(async () => {
      label.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(onExtract).toHaveBeenCalledTimes(2);
    // The sentence no longer takes row space: it is the strip's tooltip.
    expect(container.querySelector('[data-testid="sv-tab-strip-hint"]')).toBeNull();
    const strip = container.querySelector('[data-testid="sv-tab-strip"]') as HTMLElement;
    expect(strip.title).toMatch(/Drag a tab onto another Nova window/i);
    const add = container.querySelector('[data-testid="sv-tab-add"]') as HTMLButtonElement;
    expect(add.title).toMatch(/this window/i);
    await act(async () => {
      add.click();
    });
    expect(onAddDraft).toHaveBeenCalledOnce();
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('makes live tabs draggable and shows Dock only when asked', async () => {
    const onDock = vi.fn();
    const onTabDragStart = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['IPST']}
          active="IPST"
          windowId="float-1"
          showDock
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={vi.fn()}
          onDock={onDock}
          onTabDragStart={onTabDragStart}
        />,
      );
    });
    const tab = container.querySelector('[data-testid="sv-tab-IPST"]') as HTMLElement;
    expect(tab.getAttribute('draggable')).toBe('true');
    const dock = container.querySelector('[data-testid="sv-tab-dock-IPST"]') as HTMLButtonElement;
    expect(dock).toBeTruthy();
    await act(async () => {
      dock.click();
    });
    expect(onDock).toHaveBeenCalledWith('IPST');
  });

  it('hides Pop out on a float surface and does not extract on double-click', async () => {
    const onExtract = vi.fn();
    const onDock = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['F']}
          active="F"
          windowId="float-1"
          showDock
          showExtract={false}
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={onExtract}
          onDock={onDock}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-extract-F"]')).toBeNull();
    expect(container.querySelector('[data-testid="sv-tab-dock-F"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-tab-F"] .sv-tab__close')).toBeTruthy();
    const label = container.querySelector('[data-testid="sv-tab-F"] .sv-tab__label') as HTMLButtonElement;
    expect(label.title).not.toMatch(/pop out/i);
    const strip = container.querySelector('[data-testid="sv-tab-strip"]') as HTMLElement;
    expect(strip.title).toMatch(/main Nova window/i);
    await act(async () => {
      label.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(onExtract).not.toHaveBeenCalled();
  });

  it('renders tabs, marks active, and keeps + enabled past three names', async () => {
    const onAddDraft = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['AAPL', 'NUWE', 'MVO', 'IPST']}
          live={['NUWE', 'MVO', 'IPST']}
          active="NUWE"
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={onAddDraft}
          onExtract={vi.fn()}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-NUWE"]')?.className).toContain(
      'sv-tab--active',
    );
    expect(container.querySelector('[data-testid="sv-tab-AAPL"]')?.className).toContain(
      'sv-tab--suspended',
    );
    const add = container.querySelector('[data-testid="sv-tab-add"]') as HTMLButtonElement;
    expect(add.disabled).toBe(false);
    await act(async () => {
      add.click();
    });
    expect(onAddDraft).toHaveBeenCalledOnce();
  });

  it('shows the signed gap and catalyst chip from the scanner rows, one letter on inactive tabs, nothing when unknown', async () => {
    mocks.rows = rows({
      gappers: [row('GRML', 131.2, true), row('QNME', 14.6)],
      catalysts: [{
        symbol: 'QNME', previous_close: 13, current_price: 15.4, gap_percent: 14.6 / 100, volume: 0, has_news: true,
        newest_headline_at: null, catalyst_headline: 'Raises guidance', catalyst_url: null, catalyst_source: 'PR Newswire',
      }],
    });
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['GRML', 'QNME', 'ZZZZ']}
          active="GRML"
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={vi.fn()}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-gap-GRML"]')?.textContent).toBe('+131%');
    expect(container.querySelector('[data-testid="sv-tab-gap-GRML"]')?.className).toContain('sv-tab__gap--up');
    expect(container.querySelector('[data-testid="sv-tab-chip-GRML"]')?.textContent).toBe('NEWS');
    expect(container.querySelector('[data-testid="sv-tab-gap-QNME"]')?.textContent).toBe('+14.6%');
    const chip = container.querySelector('[data-testid="sv-tab-chip-QNME"]') as HTMLElement;
    expect(chip.textContent).toBe('P');
    expect(chip.title).toMatch(/^PR · Raises guidance/);
    expect(container.querySelector('[data-testid="sv-tab-gap-ZZZZ"]')).toBeNull();
    expect(container.querySelector('[data-testid="sv-tab-chip-ZZZZ"]')).toBeNull();
  });

  it('marks a recording tab with the REC dot and refuses to close it', async () => {
    mocks.recording = ['GRML'];
    const onClose = vi.fn();
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['GRML']}
          active="GRML"
          onActivate={vi.fn()}
          onClose={onClose}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={vi.fn()}
        />,
      );
    });
    expect(container.querySelector('[data-testid="sv-tab-rec-GRML"]')).toBeTruthy();
    const close = container.querySelector('[data-testid="sv-tab-close-GRML"]') as HTMLButtonElement;
    expect(close.disabled).toBe(true);
    await act(async () => { close.click(); });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('renders the trailing cluster on the same row and no overflow chevron while the tabs fit', async () => {
    await act(async () => {
      root.render(
        <StockViewTabStrip
          tabs={['GRML']}
          active="GRML"
          trailing={<span data-testid="scrubber">scrubber</span>}
          onActivate={vi.fn()}
          onClose={vi.fn()}
          onRename={vi.fn()}
          onAddDraft={vi.fn()}
          onExtract={vi.fn()}
        />,
      );
    });
    const trailing = container.querySelector('[data-testid="sv-tab-strip-trailing"]') as HTMLElement;
    expect(trailing.querySelector('[data-testid="scrubber"]')).toBeTruthy();
    expect(trailing.parentElement).toBe(container.querySelector('[data-testid="sv-tab-strip"]'));
    expect(container.querySelector('[data-testid="sv-tab-strip-overflow"]')).toBeNull();
  });
});
