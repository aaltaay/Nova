/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartGrid } from './ChartGrid';
import { ensureBarsBatch } from '../chart/barsStore';
import { clearDrawings } from '../chart/chartDrawingsStore';

vi.mock('../TickerChart', () => ({
  TickerChart: ({
    title,
    indicators,
    activeTool,
    compactChrome,
    focused,
    onFocusPane,
  }: {
    title?: string;
    indicators?: string[];
    activeTool?: string | null;
    compactChrome?: boolean;
    focused?: boolean;
    onFocusPane?: () => void;
  }) => (
    <div
      data-testid="ticker-chart"
      data-indicators={(indicators ?? []).join(',')}
      data-active-tool={activeTool ?? ''}
      data-compact={compactChrome ? '1' : '0'}
      data-focused={focused ? '1' : '0'}
      onClick={onFocusPane}
    >
      {title}
    </div>
  ),
}));

vi.mock('../chart/barsStore', () => ({
  ensureBarsBatch: vi.fn().mockResolvedValue({ results: {}, errors: {} }),
}));

vi.mock('../chart/chartDrawingsStore', () => ({
  clearDrawings: vi.fn(),
  drawingsKey: (symbol: string) => `drawings:${symbol}`,
}));

function chartTitles(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[data-testid="ticker-chart"]')].map(
    (el) => el.textContent ?? '',
  );
}

describe('ChartGrid', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    vi.mocked(ensureBarsBatch).mockClear();
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

  it('defaults to 5m|10s over Full Day|1m, with MACD on 1m and 5m', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const grid = container.querySelector('[data-testid="chart-grid"]');
    expect(grid?.classList.contains('chart-grid--row-split')).toBe(true);
    expect(container.querySelectorAll('.chart-grid__row')).toHaveLength(2);
    expect(chartTitles(container)).toEqual([
      '5-Minute',
      '10-Second',
      'Full Day',
      '1-Minute',
    ]);
    const charts = container.querySelectorAll('[data-testid="ticker-chart"]');
    const byTitle = (label: string) =>
      [...charts].find((el) => el.textContent === label) as HTMLElement;
    expect(byTitle('1-Minute')?.dataset.indicators).toContain('macd');
    expect(byTitle('5-Minute')?.dataset.indicators).toContain('macd');
    expect(byTitle('Full Day')?.dataset.indicators ?? '').not.toContain('macd');
    expect(byTitle('10-Second')?.dataset.indicators ?? '').not.toContain('macd');
    expect(byTitle('10-Second')?.dataset.indicators ?? '').not.toContain('emas');
  });

  it('can hide the 10-Second pane; 1m moves to top-right; Full Day stays bottom', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const toggle = container.querySelector(
      '[data-testid="chart-grid-optional-toggle"]',
    ) as HTMLButtonElement;
    act(() => {
      toggle.click();
    });
    expect(chartTitles(container)).toEqual([
      '5-Minute',
      '1-Minute',
      'Full Day',
    ]);
    expect(localStorage.getItem('nova.chartGrid.show10Sec')).toBe('0');
    expect(toggle.textContent).toBe('Show 10-Second');
  });

  it('queues all visible panes including 10Sec', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    expect(ensureBarsBatch).toHaveBeenCalled();
    const tfs = vi.mocked(ensureBarsBatch).mock.calls[0][1] as string[];
    expect(tfs).toEqual(['5Min', '10Sec', '1Day', '1Min']);
  });

  it('renders one desk toolbar and compact panes (no per-pane toolbars)', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    expect(container.querySelectorAll('[data-testid="chart-desk-toolbar"]')).toHaveLength(1);
    const charts = [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    expect(charts.every((el) => el.dataset.compact === '1')).toBe(true);
    // First pane is the default toggle target.
    expect(charts.map((el) => el.dataset.focused)).toEqual(['1', '0', '0', '0']);
    expect(
      container.querySelector('[data-testid="chart-desk-toolbar-target"]')?.textContent,
    ).toBe('5-Minute');
  });

  it('shared draw tool reaches every pane; indicator toggle hits only the focused pane', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const charts = () =>
      [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    const byTitle = (label: string) =>
      charts().find((el) => el.textContent === label) as HTMLElement;

    const crosshair = container.querySelector(
      '[aria-label="Use Crosshair"]',
    ) as HTMLButtonElement;
    act(() => {
      crosshair.click();
    });
    expect(charts().every((el) => el.dataset.activeTool === 'CrossLine')).toBe(true);
    act(() => {
      crosshair.click();
    });
    expect(charts().every((el) => el.dataset.activeTool === '')).toBe(true);

    // Focus Full Day, then toggle RSI: only that pane changes.
    act(() => {
      byTitle('Full Day').click();
    });
    expect(byTitle('Full Day').dataset.focused).toBe('1');
    expect(byTitle('5-Minute').dataset.focused).toBe('0');
    expect(
      container.querySelector('[data-testid="chart-desk-toolbar-target"]')?.textContent,
    ).toBe('Full Day');
    const rsiBtn = [...container.querySelectorAll<HTMLButtonElement>('.chart-tab')].find(
      (b) => b.textContent === 'RSI',
    ) as HTMLButtonElement;
    expect(rsiBtn.getAttribute('aria-pressed')).toBe('false');
    act(() => {
      rsiBtn.click();
    });
    expect(byTitle('Full Day').dataset.indicators).toContain('rsi');
    expect(byTitle('5-Minute').dataset.indicators ?? '').not.toContain('rsi');
    expect(rsiBtn.getAttribute('aria-pressed')).toBe('true');
  });

  it('Clear all wipes the symbol drawings store once and drops the active tool', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    act(() => {
      (container.querySelector('[aria-label="Use Crosshair"]') as HTMLButtonElement).click();
    });
    act(() => {
      (container.querySelector('[aria-label="Clear all drawings"]') as HTMLButtonElement).click();
    });
    expect(clearDrawings).toHaveBeenCalledTimes(1);
    expect(clearDrawings).toHaveBeenCalledWith('drawings:SDOT');
    const charts = [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    expect(charts.every((el) => el.dataset.activeTool === '')).toBe(true);
  });

  it('hiding 10-Second while it is focused falls back to the first pane', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const byTitle = (label: string) =>
      [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')].find(
        (el) => el.textContent === label,
      ) as HTMLElement;
    act(() => {
      byTitle('10-Second').click();
    });
    expect(
      container.querySelector('[data-testid="chart-desk-toolbar-target"]')?.textContent,
    ).toBe('10-Second');
    act(() => {
      (container.querySelector('[data-testid="chart-grid-optional-toggle"]') as HTMLButtonElement).click();
    });
    expect(
      container.querySelector('[data-testid="chart-desk-toolbar-target"]')?.textContent,
    ).toBe('5-Minute');
  });
});
