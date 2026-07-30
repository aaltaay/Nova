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

  it('batch-warms default panes but excludes 10Sec', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    expect(ensureBarsBatch).toHaveBeenCalled();
    const tfs = vi.mocked(ensureBarsBatch).mock.calls[0][1] as string[];
    expect(tfs).toEqual(['5Min', '1Day', '1Min']);
    expect(tfs).not.toContain('10Sec');
  });
});
