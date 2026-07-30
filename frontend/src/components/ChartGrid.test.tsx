/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartGrid } from './ChartGrid';
import { ensureBarsBatch } from '../chart/barsStore';

vi.mock('../TickerChart', () => ({
  TickerChart: ({
    title,
    initialIndicators,
  }: {
    title?: string;
    initialIndicators?: string[];
  }) => (
    <div
      data-testid="ticker-chart"
      data-indicators={(initialIndicators ?? []).join(',')}
    >
      {title}
    </div>
  ),
}));

vi.mock('../chart/barsStore', () => ({
  ensureBarsBatch: vi.fn().mockResolvedValue({ results: {}, errors: {} }),
}));

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

  it('defaults to 4 panes including 10-Second, with MACD on 1m and 5m', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const grid = container.querySelector('[data-testid="chart-grid"]');
    expect(grid?.classList.contains('chart-grid--row-split')).toBe(true);
    expect(container.querySelectorAll('.chart-grid__row')).toHaveLength(2);
    expect(
      container.querySelector('.resize-handle--horizontal[aria-label="Resize chart rows"]'),
    ).toBeTruthy();
    const charts = container.querySelectorAll('[data-testid="ticker-chart"]');
    expect(charts).toHaveLength(4);
    expect(container.textContent).toContain('10-Second');
    const byTitle = (label: string) =>
      [...charts].find((el) => el.textContent === label) as HTMLElement;
    expect(byTitle('1-Minute')?.dataset.indicators).toContain('macd');
    expect(byTitle('5-Minute')?.dataset.indicators).toContain('macd');
    expect(byTitle('Full Day')?.dataset.indicators ?? '').not.toContain('macd');
    const toggle = container.querySelector(
      '[data-testid="chart-grid-optional-toggle"]',
    ) as HTMLButtonElement;
    expect(toggle.textContent).toBe('Hide 10-Second');
  });

  it('can hide the 10-Second fourth pane and persist', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const toggle = container.querySelector(
      '[data-testid="chart-grid-optional-toggle"]',
    ) as HTMLButtonElement;
    act(() => {
      toggle.click();
    });
    expect(container.querySelectorAll('[data-testid="ticker-chart"]')).toHaveLength(3);
    expect(localStorage.getItem('nova.chartGrid.show10Sec')).toBe('0');
    expect(toggle.textContent).toBe('Show 10-Second');
  });

  it('batch-warms default panes but excludes 10Sec', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    expect(ensureBarsBatch).toHaveBeenCalled();
    const tfs = vi.mocked(ensureBarsBatch).mock.calls[0][1] as string[];
    expect(tfs).toEqual(['1Min', '5Min', '1Day']);
    expect(tfs).not.toContain('10Sec');
  });
});
