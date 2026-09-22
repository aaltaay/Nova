/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EmptyState } from './EmptyState';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, gateway_mode: 'paper' }),
}));

vi.mock('../ibkr/useIbkrReconnectWarmup', () => ({
  useIbkrReconnectWarmup: () => false,
}));

describe('EmptyState history', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('does not use live market-closed copy when viewing a past date', async () => {
    await act(() => {
      root.render(
        <EmptyState
          health={{ status: 'ok', latency_ms: 1 }}
          context="closed"
          discoveryProvider="ibkr"
          historyDate="2026-08-24"
          emptyLabel="gappers"
        />,
      );
    });
    expect(container.textContent).toContain('No saved gappers for 2026-08-24');
    expect(container.textContent).not.toContain('Market is closed');
    expect(container.textContent).not.toContain('Scanning continues');
  });

  it('honest-empty Large Cap uses the shared history copy, not live L1', async () => {
    await act(() => {
      root.render(
        <EmptyState
          health={{ status: 'ok', latency_ms: 1 }}
          context="market"
          discoveryProvider="ibkr"
          historyDate="2026-09-15"
          emptyLabel="large cap movers"
        />,
      );
    });
    expect(container.textContent).toContain('No saved large cap movers for 2026-09-15');
    expect(container.textContent).not.toContain('in the feed right now');
  });

  it('closed session does not treat an unavailable roster as a feed death', async () => {
    await act(() => {
      root.render(
        <EmptyState
          health={{ status: 'ok', latency_ms: 1 }}
          context="closed"
          discoveryProvider="ibkr"
          emptyLabel="gainers"
          honestyHint="Unavailable -- no live roster"
        />,
      );
    });
    expect(container.textContent).toMatch(/Market is closed/);
    expect(container.textContent).not.toMatch(/not a quiet market/);
    expect(container.textContent).not.toMatch(/Unavailable -- no live roster/);
  });

  it('never claims "showing last available data" over an empty closed-session list (QA V25)', async () => {
    await act(() => {
      root.render(
        <EmptyState
          health={{ status: 'ok', latency_ms: 1 }}
          context="closed"
          discoveryProvider="ibkr"
          emptyLabel="gappers"
        />,
      );
    });
    expect(container.textContent).toMatch(/Market is closed/);
    expect(container.textContent).not.toMatch(/showing last available data/);
    expect(container.textContent).toMatch(/no gappers on this list/);
  });

  it('states a failed scanner route before any closed or loading copy (QA C31)', async () => {
    for (const context of ['closed', 'loading', 'market'] as const) {
      await act(() => {
        root.render(
          <EmptyState
            health={{ status: 'ok', latency_ms: 1 }}
            context={context}
            discoveryProvider="ibkr"
            emptyLabel="gainers"
            feedFailure="Scanner feed failed: /api/movers answered HTTP 500"
          />,
        );
      });
      expect(container.textContent).toMatch(/\/api\/movers answered HTTP 500/);
      expect(container.textContent).not.toMatch(/Market is closed|Loading market data/);
    }
  });

  it('does not point at the HOD integrity banner, and paints feed_error', async () => {
    await act(() => {
      root.render(
        <EmptyState
          health={{ status: 'ok', latency_ms: 1 }}
          context="premarket"
          discoveryProvider="ibkr"
          emptyLabel="gappers"
          honestyHint="gappers: TimeoutError"
        />,
      );
    });
    expect(container.textContent).toMatch(/gappers: TimeoutError/);
    expect(container.textContent).not.toMatch(/integrity banner/);
  });
});
