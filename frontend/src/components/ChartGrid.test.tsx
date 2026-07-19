/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartGrid } from './ChartGrid';

vi.mock('../TickerChart', () => ({
  TickerChart: ({ title }: { title?: string }) => (
    <div data-testid="ticker-chart">{title}</div>
  ),
}));

describe('ChartGrid', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
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

  it('renders two rows with a horizontal resize handle between them', () => {
    act(() => {
      root.render(<ChartGrid symbol="SDOT" />);
    });
    const grid = container.querySelector('[data-testid="chart-grid"]');
    expect(grid?.classList.contains('chart-grid--row-split')).toBe(true);
    expect(container.querySelectorAll('.chart-grid__row')).toHaveLength(2);
    expect(
      container.querySelector('.resize-handle--horizontal[aria-label="Resize chart rows"]'),
    ).toBeTruthy();
    expect(container.querySelectorAll('[data-testid="ticker-chart"]')).toHaveLength(4);
  });
});
