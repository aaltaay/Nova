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
    maximized,
    maximizeInGrid,
    onMaximizeChange,
  }: {
    title?: string;
    indicators?: string[];
    activeTool?: string | null;
    compactChrome?: boolean;
    focused?: boolean;
    onFocusPane?: () => void;
    maximized?: boolean;
    maximizeInGrid?: boolean;
    onMaximizeChange?: (next: boolean) => void;
  }) => (
    <div
      data-testid="ticker-chart"
      data-indicators={(indicators ?? []).join(',')}
      data-active-tool={activeTool ?? ''}
      data-compact={compactChrome ? '1' : '0'}
      data-focused={focused ? '1' : '0'}
      data-maximized={maximized ? '1' : '0'}
      data-maximize-in-grid={maximizeInGrid ? '1' : '0'}
      onClick={onFocusPane}
    >
      <button
        type="button"
        aria-label={maximized ? 'Restore chart' : 'Maximize chart'}
        onClick={() => onMaximizeChange?.(!(maximized ?? false))}
      />
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
    document.body.querySelector('[data-testid="chart-draw-tools-menu"]')?.remove();
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
    expect(JSON.parse(localStorage.getItem('nova.chartGrid.show10Sec') ?? '').value).toBe(false);
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

  it('desk toolbar dropdown opens and arms Trendline on every pane', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    act(() => {
      (container.querySelector('[aria-label="Line drawing tools"]') as HTMLButtonElement).click();
    });
    const menu = document.body.querySelector('[data-testid="chart-draw-tools-menu"]');
    expect(menu).not.toBeNull();
    const trend = [...(menu?.querySelectorAll('button') ?? [])].find((button) =>
      button.textContent?.includes('Trendline'),
    ) as HTMLButtonElement;
    act(() => {
      trend.click();
    });
    const charts = [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    expect(charts.every((el) => el.dataset.activeTool === 'TrendLine')).toBe(true);
    expect(document.body.querySelector('[data-testid="chart-draw-tools-menu"]')).toBeNull();
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

  it('double-click maximizes one pane inside the chart grid and keeps its indicators', () => {
    act(() => {
      root.render(<ChartGrid symbol="TNON" />);
    });
    const cell = container.querySelector(
      '[data-testid="chart-grid-cell-1Min"]',
    ) as HTMLElement;
    const before = cell.querySelector('[data-testid="ticker-chart"]') as HTMLElement;
    expect(before.dataset.indicators).toContain('macd');
    act(() => {
      cell.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    const grid = container.querySelector('[data-testid="chart-grid"]') as HTMLElement;
    expect(grid.classList.contains('chart-grid--pane-maximized')).toBe(true);
    expect(grid.dataset.maximizedPane).toBe('1Min');
    expect(cell.classList.contains('chart-grid-cell--maximized')).toBe(true);
    expect(cell.dataset.maximized).toBe('1');
    const after = cell.querySelector('[data-testid="ticker-chart"]') as HTMLElement;
    expect(after.dataset.maximized).toBe('1');
    expect(after.dataset.maximizeInGrid).toBe('1');
    expect(after.dataset.indicators).toContain('macd');
    expect(after.textContent).toContain('1-Minute');
    expect(container.querySelector('[data-testid="chart-grid-restore"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="chart-desk-toolbar"]')).toBeTruthy();
  });

  it('restores the 2x2 from a second double-click, Esc, or Restore grid', () => {
    act(() => {
      root.render(<ChartGrid symbol="TNON" />);
    });
    const cell = () =>
      container.querySelector('[data-testid="chart-grid-cell-5Min"]') as HTMLElement;
    const grid = () =>
      container.querySelector('[data-testid="chart-grid"]') as HTMLElement;

    act(() => {
      cell().dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(grid().dataset.maximizedPane).toBe('5Min');

    act(() => {
      cell().dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    expect(grid().dataset.maximizedPane).toBe('');
    expect(grid().classList.contains('chart-grid--pane-maximized')).toBe(false);

    act(() => {
      cell().dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(grid().dataset.maximizedPane).toBe('');

    act(() => {
      cell().dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    act(() => {
      (container.querySelector('[data-testid="chart-grid-restore"]') as HTMLButtonElement).click();
    });
    expect(grid().dataset.maximizedPane).toBe('');
  });

  it('does not maximize on double-click while a drawing tool is armed', () => {
    act(() => {
      root.render(<ChartGrid symbol="TNON" />);
    });
    act(() => {
      (container.querySelector('[aria-label="Use Crosshair"]') as HTMLButtonElement).click();
    });
    act(() => {
      (container.querySelector('[data-testid="chart-grid-cell-5Min"]') as HTMLElement)
        .dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
    const grid = container.querySelector('[data-testid="chart-grid"]') as HTMLElement;
    expect(grid.dataset.maximizedPane).toBe('');
    const charts = [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    expect(charts.every((el) => el.dataset.activeTool === 'CrossLine')).toBe(true);
  });

  it('Esc disarms the drawing tool before restoring a maximized pane', () => {
    act(() => {
      root.render(<ChartGrid symbol="TNON" />);
    });
    act(() => {
      (
        container.querySelector(
          '[data-testid="chart-grid-cell-5Min"] [aria-label="Maximize chart"]',
        ) as HTMLButtonElement
      ).click();
    });
    act(() => {
      (container.querySelector('[aria-label="Use Crosshair"]') as HTMLButtonElement).click();
    });
    const grid = () =>
      container.querySelector('[data-testid="chart-grid"]') as HTMLElement;
    expect(grid().dataset.maximizedPane).toBe('5Min');
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(grid().dataset.maximizedPane).toBe('5Min');
    const charts = [...container.querySelectorAll<HTMLElement>('[data-testid="ticker-chart"]')];
    expect(charts.every((el) => el.dataset.activeTool === '')).toBe(true);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(grid().dataset.maximizedPane).toBe('');
  });

  it('clears maximize when the expanded 10-Second pane is hidden', () => {
    act(() => {
      root.render(<ChartGrid symbol="TNON" />);
    });
    act(() => {
      (
        container.querySelector(
          '[data-testid="chart-grid-cell-10Sec"] [aria-label="Maximize chart"]',
        ) as HTMLButtonElement
      ).click();
    });
    expect(
      (container.querySelector('[data-testid="chart-grid"]') as HTMLElement).dataset
        .maximizedPane,
    ).toBe('10Sec');
    act(() => {
      (container.querySelector('[data-testid="chart-grid-optional-toggle"]') as HTMLButtonElement)
        .click();
    });
    expect(
      (container.querySelector('[data-testid="chart-grid"]') as HTMLElement).dataset
        .maximizedPane,
    ).toBe('');
    expect(container.querySelector('[data-testid="chart-grid-cell-10Sec"]')).toBeNull();
  });
});
