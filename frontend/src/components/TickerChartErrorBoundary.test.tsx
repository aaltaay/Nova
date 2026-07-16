/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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

  it('isolates a child crash and offers retry', async () => {
    await act(async () => {
      root.render(
        <TickerChartErrorBoundary>
          <Boom />
        </TickerChartErrorBoundary>,
      );
    });
    expect(container.textContent).toMatch(/Chart unavailable/);
    expect(container.querySelector('button')?.textContent).toMatch(/Retry chart/);
  });
});
