/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';

vi.mock('./BackendStartButton', () => ({
  BackendStartButton: () => <button type="button">Start API</button>,
}));

const healthy = {
  status: 'connected',
  latency_ms: 610,
};

describe('HeaderConnectionStatus', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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

  it('labels API separately from Gateway and Prices when discovery is ibkr', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected={false}
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={59915}
          pricesStale
          historyDate={null}
        />,
      );
    });

    const api = container.querySelector('[data-testid="status-chip-api"]');
    const gateway = container.querySelector('[data-testid="status-chip-gateway"]');
    const prices = container.querySelector('[data-testid="status-chip-prices"]');

    expect(api?.textContent).toMatch(/API/);
    expect(api?.textContent).toMatch(/up/);
    expect(api?.textContent).toMatch(/610ms/);
    expect(api?.textContent).not.toMatch(/Connected/i);

    expect(gateway?.textContent).toMatch(/Gateway/);
    expect(gateway?.textContent).toMatch(/offline/);

    expect(prices?.textContent).toMatch(/Prices/);
    expect(prices?.textContent).toMatch(/16h ago/);
    expect(prices?.textContent).toMatch(/stale/);
  });

  it('shows Alpaca feed chip instead of Gateway when discovery is alpaca', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="alpaca"
          ibkrConnected={false}
          activeFeed="iex"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });

    const feed = container.querySelector('[data-testid="status-chip-feed"]');
    expect(feed?.textContent).toMatch(/Alpaca IEX/);
    expect(container.querySelector('[data-testid="status-chip-gateway"]')).toBeNull();
  });
});
