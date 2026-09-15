/**
 * @vitest-environment jsdom
 */
import { act, useEffect, useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdvisePanel } from './AdvisePanel';
import { AdviseProvider, useAdvise } from './AdviseContext';
import * as api from './adviseApi';
import { ADVISE_ESTIMATE_DEBOUNCE_MS } from './constants';
import type { AdviseEstimate, AdviseRun } from './types';

const workspace = {
  selectedSymbol: 'AAPL' as string | null,
  activeTraderSymbol: null as string | null,
  openStockView: vi.fn(),
};

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

function estimateFor(symbol: string, depth: number): AdviseEstimate {
  const usd = Number((0.1 * depth).toFixed(2));
  return {
    symbol,
    depth,
    model: 'sonnet',
    model_label: 'Claude Sonnet',
    llm_calls: 10 + depth * 2,
    est_usd: usd,
    est_minutes: depth * 2,
    summary: `~$${usd.toFixed(2)} and ~${depth * 2} min for ${depth} debate round(s)`,
    disclaimer: 'Advisory only -- not financial advice and not auto-trading.',
    note: 'Rough only',
  };
}

function OpenOnce() {
  const { openAdvise, open } = useAdvise();
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    openAdvise();
  }, [openAdvise]);
  return open ? <AdvisePanel /> : null;
}

describe('Advise estimate and spend gates', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    workspace.selectedSymbol = 'AAPL';
    workspace.activeTraderSymbol = null;
    workspace.openStockView.mockClear();
    vi.spyOn(api, 'fetchAdviseLatest').mockResolvedValue(null);
    vi.spyOn(api, 'fetchAdviseHistory').mockResolvedValue([]);
    vi.spyOn(api, 'fetchAdviseEstimate').mockImplementation(async (symbol, depth) => (
      estimateFor(symbol, depth)
    ));
    vi.spyOn(api, 'postAdviseRun').mockResolvedValue({
      id: 1,
      symbol: 'AAPL',
      status: 'queued',
    } as AdviseRun);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  async function renderOpen(): Promise<void> {
    await act(async () => {
      root.render(
        <AdviseProvider>
          <OpenOnce />
        </AdviseProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it('shows the loud cost line after open with desk prefill', async () => {
    await renderOpen();
    const headline = container.querySelector('[data-testid="advise-estimate-headline"]');
    expect(headline?.textContent).toBe('~$0.20 · ~4 min');
    expect(container.querySelector('[data-testid="advise-estimate-summary"]')?.textContent)
      .toMatch(/2 debate/);
    expect(api.fetchAdviseEstimate).toHaveBeenCalledWith('AAPL', 2);
  });

  it('refreshes estimate when a symbol is typed without blur', async () => {
    vi.useFakeTimers();
    workspace.selectedSymbol = null;
    await renderOpen();
    expect(container.querySelector('[data-testid="advise-empty-hint"]')).toBeTruthy();
    expect(api.fetchAdviseEstimate).not.toHaveBeenCalled();
    const input = container.querySelector('[data-testid="advise-symbol"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { value: 'MSFT' } });
    });
    expect(api.fetchAdviseEstimate).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADVISE_ESTIMATE_DEBOUNCE_MS);
    });
    expect(api.fetchAdviseEstimate).toHaveBeenCalledWith('MSFT', 2);
    expect(container.querySelector('[data-testid="advise-estimate-headline"]')?.textContent)
      .toBe('~$0.20 · ~4 min');
  });

  it('still shows estimate when latest and history fail', async () => {
    vi.spyOn(api, 'fetchAdviseLatest').mockRejectedValue(new Error('book down'));
    vi.spyOn(api, 'fetchAdviseHistory').mockRejectedValue(new Error('history down'));
    await renderOpen();
    expect(container.querySelector('[data-testid="advise-estimate-headline"]')?.textContent)
      .toBe('~$0.20 · ~4 min');
    expect(container.querySelector('[data-testid="advise-error"]')?.textContent)
      .toMatch(/book down/);
  });

  it('keeps Run disabled and skips spend when the symbol is empty', async () => {
    workspace.selectedSymbol = null;
    await renderOpen();
    const run = container.querySelector('[data-testid="advise-run"]') as HTMLButtonElement;
    expect(run.disabled).toBe(true);
    expect(container.querySelector('[data-testid="advise-empty-hint"]')).toBeTruthy();
    expect(api.postAdviseRun).not.toHaveBeenCalled();
    await act(async () => {
      run.click();
    });
    expect(api.postAdviseRun).not.toHaveBeenCalled();
  });

  it('recalculates a higher cost when depth increases', async () => {
    vi.useFakeTimers();
    await renderOpen();
    const depth = container.querySelector('[data-testid="advise-depth"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(depth, { target: { value: '5' } });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADVISE_ESTIMATE_DEBOUNCE_MS);
    });
    expect(api.fetchAdviseEstimate).toHaveBeenCalledWith('AAPL', 5);
    expect(container.querySelector('[data-testid="advise-estimate-headline"]')?.textContent)
      .toBe('~$0.50 · ~10 min');
  });
});
