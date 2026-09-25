/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CHART_CRASH_AUTO_RETRY_MS } from '../constants';
import { reportClientError } from '../utils/reportClientError';
import { TickerChartErrorBoundary } from './TickerChartErrorBoundary';

vi.mock('../utils/reportClientError', () => ({
  reportClientError: vi.fn(),
}));

function Boom(): never {
  throw new Error('chart boom');
}

describe('TickerChartErrorBoundary', () => {
  let container: HTMLDivElement;
  let root: Root;
  let consoleError: typeof console.error;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    consoleError = console.error;
    console.error = vi.fn();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    console.error = consoleError;
  });

  it('isolates a child crash, says why and offers retry', async () => {
    await act(async () => {
      root.render(
        <TickerChartErrorBoundary label="1Min">
          <Boom />
        </TickerChartErrorBoundary>,
      );
    });
    expect(container.textContent).toMatch(/Chart unavailable/);
    expect(container.querySelector('[data-testid="chart-crashed-reason"]')?.textContent).toBe('chart boom');
    expect(container.querySelector('button')?.textContent).toMatch(/Retry chart/);
    expect(reportClientError).toHaveBeenCalledWith(expect.objectContaining({ source: 'ticker-chart:1Min' }));
  });

  it('draws the pane again once on its own', async () => {
    vi.useFakeTimers();
    try {
      let broken = true;
      const Flaky = () => {
        if (broken) throw new Error('mid-change');
        return <span>chart drawn</span>;
      };
      await act(async () => {
        root.render(<TickerChartErrorBoundary><Flaky /></TickerChartErrorBoundary>);
      });
      expect(container.textContent).toMatch(/Drawing it again/);
      broken = false;
      await act(async () => {
        vi.advanceTimersByTime(CHART_CRASH_AUTO_RETRY_MS);
      });
      expect(container.textContent).toBe('chart drawn');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a second crash right after the automatic retry waits for the operator', async () => {
    vi.useFakeTimers();
    try {
      let broken = true;
      const Flaky = () => {
        if (broken) throw new Error('mid-change');
        return <span>chart drawn</span>;
      };
      await act(async () => {
        root.render(<TickerChartErrorBoundary><Flaky /></TickerChartErrorBoundary>);
      });
      await act(async () => {
        vi.advanceTimersByTime(CHART_CRASH_AUTO_RETRY_MS);
      });
      expect(container.textContent).toMatch(/Chart unavailable/);
      expect(container.textContent).not.toMatch(/Drawing it again/);
      await act(async () => {
        vi.advanceTimersByTime(CHART_CRASH_AUTO_RETRY_MS * 5);
      });
      expect(container.textContent).toMatch(/Chart unavailable/);
      broken = false;
      await act(async () => {
        (container.querySelector('[data-testid="chart-crashed-retry"]') as HTMLButtonElement).click();
      });
      expect(container.textContent).toBe('chart drawn');
    } finally {
      vi.useRealTimers();
    }
  });
});
