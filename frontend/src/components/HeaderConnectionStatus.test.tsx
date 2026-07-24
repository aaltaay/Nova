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
  health_source: 'alpaca_account_api',
  latency_source: 'alpaca_account_http',
  market_data_source: 'ibkr',
  integrations: {
    alpaca: { status: 'ok', detail: 'news/listing/RVOL aux, not live prices' },
    openai: { status: 'off', detail: 'Lincoln off' },
    yfinance: { status: 'ok', detail: 'importable' },
    archive: { status: 'off', detail: 'R2 disabled' },
  },
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

  it('attributes Alpaca account RTT separately from Gateway and Prices', () => {
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
    expect(api?.textContent).toMatch(/Alpaca account RTT 610ms/);
    expect(api?.textContent).not.toMatch(/up\s*·\s*610ms/);
    expect(api?.textContent).not.toMatch(/Connected/i);

    expect(gateway?.textContent).toMatch(/Gateway/);
    expect(gateway?.textContent).toMatch(/offline/);
    expect(gateway?.textContent).not.toMatch(/610ms/);

    expect(prices?.textContent).toMatch(/Prices/);
    expect(prices?.textContent).toMatch(/16h ago/);
    expect(prices?.textContent).toMatch(/stale/);

    const alpacaAux = container.querySelector('[data-testid="status-chip-integration-alpaca"]');
    const openai = container.querySelector('[data-testid="status-chip-integration-openai"]');
    expect(alpacaAux?.textContent).toMatch(/News/);
    expect(alpacaAux?.textContent).toMatch(/ok/);
    expect(openai?.textContent).toMatch(/OpenAI/);
    expect(openai?.textContent).toMatch(/off/);
    // Under IBKR discovery, price feed chip must stay Gateway — not "Alpaca IEX"
    expect(container.querySelector('[data-testid="status-chip-feed"]')).toBeNull();
  });

  it('omits legacy latency when its source is unavailable', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={{ ...healthy, latency_source: undefined }}
          discoveryProvider="ibkr"
          ibkrConnected
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });

    const api = container.querySelector('[data-testid="status-chip-api"]');
    expect(api?.textContent).toMatch(/API/);
    expect(api?.textContent).toMatch(/up/);
    expect(api?.textContent).not.toMatch(/610ms/);
    expect(api?.getAttribute('title')).toMatch(/No source-attributed RTT/);
  });

  it('labels Gateway paper vs LIVE so session money path is never ambiguous', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          ibkrMode="paper"
          ibkrGatewayMode="paper"
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="status-chip-gateway"]')?.textContent,
    ).toMatch(/connected\s*·\s*PAPER/i);

    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          ibkrMode="live"
          ibkrGatewayMode="live"
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });
    const liveGateway = container.querySelector('[data-testid="status-chip-gateway"]');
    expect(liveGateway?.textContent).toMatch(/connected\s*·\s*LIVE/i);
    expect(liveGateway?.className).toMatch(/status-chip--live/);
  });

  it('legacy alpaca discovery prop still shows Feed chip (dead product path)', () => {
    // Product lock prevents Settings from selecting alpaca; keep branch coverage.
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
