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
});
