/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import type { CaptureSessions } from '../sim/useSimSessionController';
import { formatMissingSeconds, RecordsPage, todayEasternDate } from './RecordsPage';

const { captures, status } = vi.hoisted(() => ({
  captures: {
    state: { data: null as CaptureSessions | null, error: null as string | null },
    listeners: new Set<() => void>(),
  },
  status: { current: {} as IbkrClientStatus },
}));

vi.mock('../sim/useSimSessionController', () => ({
  capturesResource: {
    getSnapshot: () => captures.state,
    subscribe: (l: () => void) => {
      captures.listeners.add(l);
      return () => captures.listeners.delete(l);
    },
  },
}));
vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));

function publish(next: typeof captures.state) {
  captures.state = next;
  captures.listeners.forEach((l) => l());
}

describe('RecordsPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  const onOpenTrader = vi.fn();

  beforeEach(() => {
    onOpenTrader.mockReset();
    captures.state = { data: null, error: null };
    status.current = { connected: true, stale: false } as IbkrClientStatus;
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

  function render() {
    act(() => {
      root.render(<RecordsPage onOpenTrader={onOpenTrader} />);
    });
  }

  it('formats Eastern dates and missing seconds', () => {
    expect(todayEasternDate(new Date('2026-09-21T03:30:00Z'))).toBe('2026-09-20');
    expect(todayEasternDate(new Date('2026-09-21T12:30:00Z'))).toBe('2026-09-21');
    expect(formatMissingSeconds(undefined)).toBe('--');
    expect(formatMissingSeconds(0)).toBe('--');
    expect(formatMissingSeconds(42)).toBe('42s');
    expect(formatMissingSeconds(65)).toBe('1m 05s');
  });

  it('states loading, then today\'s rows with a Trader link, marking the recording symbol', () => {
    status.current = { connected: true, stale: false, capture: true, recording: true, capture_symbols: ['GRML'] } as IbkrClientStatus;
    render();
    expect(container.textContent).toMatch(/Loading Session Records/);
    const today = todayEasternDate();
    act(() => {
      publish({
        data: {
          days: [{ date: today, ticker_count: 2 }, { date: '2020-01-02', ticker_count: 1 }],
          tickers_by_day: {
            [today]: [
              { symbol: 'GRML', prints: 1234, l2: 10, segments: 2, missing_sec: 65, usable: true },
              { symbol: 'IMCC', prints: 5, l2: 0, segments: 1, missing_sec: 0, empty: true, usable: false },
            ],
            '2020-01-02': [{ symbol: 'OLD', prints: 1, l2: 0 }],
          },
        },
        error: null,
      });
    });
    expect(container.querySelector('[data-testid="records-page-recording"]')!.textContent).toMatch(/GRML/);
    const grml = container.querySelector('[data-testid="records-row-GRML"]')!;
    expect(grml.textContent).toMatch(/1,234/);
    expect(grml.textContent).toMatch(/1m 05s/);
    expect(grml.textContent).toMatch(/Recording/);
    expect(container.querySelector('[data-testid="records-row-IMCC"]')!.textContent).toMatch(/empty/);
    expect(container.querySelector('[data-testid="records-row-OLD"]')).toBeNull();
    act(() => {
      (container.querySelector('[data-testid="records-open-GRML"]') as HTMLButtonElement).click();
    });
    expect(onOpenTrader).toHaveBeenCalledWith('GRML');
  });

  it('says so when there are no Session Records today and when the listing is unavailable', () => {
    render();
    act(() => {
      publish({ data: { days: [], tickers_by_day: {} }, error: null });
    });
    expect(container.querySelector('[data-testid="records-page-empty"]')).toBeTruthy();
    act(() => {
      publish({ data: null, error: 'HTTP 503' });
    });
    expect(container.querySelector('[role="alert"]')!.textContent).toMatch(/unavailable: HTTP 503/);
  });
});
