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

vi.mock('./BackendReloadButton', () => ({
  BackendReloadButton: () => <button type="button">Reload backend</button>,
}));

vi.mock('../utils/startLocalApi', () => ({
  canReloadLocalBackend: () => true,
  startLocalApi: vi.fn(),
}));

const ibkrStatusMock = vi.hoisted(() => ({
  market_data_delayed: false as boolean,
  market_data_type: 1 as number | null,
  completed_orders_unanswered_since: null as number | null,
}));

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: true,
    mode: 'paper',
    market_data_type: ibkrStatusMock.market_data_type,
    market_data_delayed: ibkrStatusMock.market_data_delayed,
    completed_orders_unanswered_since: ibkrStatusMock.completed_orders_unanswered_since,
    disconnect_hint: null,
  }),
  refreshIbkrStatusNow: () => {},
}));

const healthy = {
  status: 'connected',
  latency_ms: 0,
  health_source: 'nova_process',
  latency_source: 'none',
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
    ibkrStatusMock.market_data_delayed = false;
    ibkrStatusMock.market_data_type = 1;
    ibkrStatusMock.completed_orders_unanswered_since = null;
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

  it('Desk chip is Nova API + Gateway — no Alpaca RTT or Alpaca chip', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={{
            ...healthy,
            latency_ms: 610,
            latency_source: 'alpaca_account_http',
          }}
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

    const desk = container.querySelector('[data-testid="status-chip-desk"]');
    const prices = container.querySelector('[data-testid="status-chip-prices"]');

    expect(container.querySelector('[data-testid="status-chip-api"]')).toBeNull();
    expect(container.querySelector('[data-testid="status-chip-gateway"]')).toBeNull();
    expect(desk?.textContent).toMatch(/Desk/);
    expect(desk?.textContent).toMatch(/offline/);
    expect(desk?.textContent).not.toMatch(/Alpaca/i);
    expect(desk?.textContent).not.toMatch(/610ms/);
    expect(desk?.getAttribute('title')).toMatch(/port 8000/);

    expect(prices?.textContent).toMatch(/Prices/);
    expect(prices?.textContent).toMatch(/16h ago/);
    expect(prices?.textContent).toMatch(/stale/);

    expect(container.querySelector('[data-testid="status-chip-integration-alpaca"]')).toBeNull();
    const openai = container.querySelector('[data-testid="status-chip-integration-openai"]');
    expect(openai?.textContent).toMatch(/OpenAI/);
    expect(openai?.textContent).toMatch(/off/);
    expect(container.querySelector('[data-testid="status-chip-feed"]')).toBeNull();
  });

  it('places an ET clock next to Desk without a session label', () => {
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
    const clock = container.querySelector('[data-testid="header-market-clock"]');
    expect(clock?.textContent).toMatch(/\d{2}:\d{2}:\d{2} ET/);
    expect(clock?.textContent).not.toMatch(/After-hours|Premarket|\bRTH\b|Closed|AFTER HOURS/i);
    const desk = container.querySelector('[data-testid="status-chip-desk"]');
    expect(desk).toBeTruthy();
  });

  it('Desk chip is connection only -- up / delayed / offline; mode lives on the capsule', () => {
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
    const paperDesk = container.querySelector('[data-testid="status-chip-desk"]');
    expect(paperDesk?.textContent).toMatch(/Desk\s*up/i);
    expect(paperDesk?.textContent).not.toMatch(/PAPER|LIVE/i);
    expect(paperDesk?.className).toMatch(/status-chip--ok/);
    expect(paperDesk?.className).not.toMatch(/status-chip--live/);

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
    const liveDesk = container.querySelector('[data-testid="status-chip-desk"]');
    expect(liveDesk?.textContent).toMatch(/Desk\s*up/i);
    expect(liveDesk?.textContent).not.toMatch(/PAPER|LIVE/i);
    expect(liveDesk?.className).toMatch(/status-chip--ok/);
    expect(liveDesk?.className).not.toMatch(/status-chip--live/);
  });

  it('shows a Paper | Live capsule — paper orange, live green — next to Gateway', () => {
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
    const capsule = container.querySelector('[data-testid="header-gateway-mode-capsule"]');
    expect(capsule).toBeTruthy();
    const segs = capsule!.querySelectorAll('.gw-mode-capsule__seg');
    expect(segs).toHaveLength(3);
    expect(segs[0].textContent).toMatch(/Paper/i);
    expect(segs[1].textContent).toMatch(/Live/i);
    expect(segs[2].textContent).toMatch(/Sim/i);
    expect(capsule!.classList.contains('is-paper')).toBe(true);
    expect(segs[0].classList.contains('is-selected')).toBe(true);
    expect(segs[0].classList.contains('is-paper')).toBe(true);
    expect(segs[1].classList.contains('is-selected')).toBe(false);

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
    const liveCapsule = container.querySelector('[data-testid="header-gateway-mode-capsule"]');
    const liveSegs = liveCapsule!.querySelectorAll('.gw-mode-capsule__seg');
    expect(liveCapsule!.classList.contains('is-live')).toBe(true);
    expect(liveSegs[1].classList.contains('is-selected')).toBe(true);
    expect(liveSegs[1].classList.contains('is-live')).toBe(true);
    expect(liveSegs[0].classList.contains('is-selected')).toBe(false);
  });

  it('hides Prices chip when secondsAgo is null (non-scanner tab)', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={null}
          pricesStale
          historyDate={null}
        />,
      );
    });

    expect(container.querySelector('[data-testid="status-chip-prices"]')).toBeNull();
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
    expect(container.querySelector('[data-testid="status-chip-desk"]')).toBeNull();
    expect(container.querySelector('[data-testid="status-chip-api"]')).not.toBeNull();
  });

  it('opens Trading prerequisites when the Desk chip is clicked', () => {
    const opened: string[] = [];
    const onOpen = () => opened.push('open');
    window.addEventListener('nova-trading-prereq-open', onOpen);
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected={false}
          ibkrMode="disconnected"
          ibkrGatewayMode="live"
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });
    const desk = container.querySelector('[data-testid="status-chip-desk"]') as HTMLButtonElement;
    act(() => {
      desk.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    window.removeEventListener('nova-trading-prereq-open', onOpen);
    expect(opened).toEqual(['open']);
  });

  it('shows amber delayed on Desk chip when market_data_delayed', () => {
    ibkrStatusMock.market_data_delayed = true;
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
    const desk = container.querySelector('[data-testid="status-chip-desk"]');
    expect(desk?.textContent).toMatch(/delayed/i);
    expect(desk?.className).toMatch(/status-chip--warn/);
  });

  it('turns the Desk chip amber when the Gateway stops answering completed orders (D-058)', () => {
    ibkrStatusMock.completed_orders_unanswered_since = 1789808049;
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
    const desk = container.querySelector('[data-testid="status-chip-desk"]');
    expect(desk?.className).toMatch(/status-chip--warn/);
    expect(desk?.getAttribute('title')).toMatch(/Completed orders not answering since/);
    expect(desk?.getAttribute('title')).toMatch(/Restart IB Gateway when convenient/);
  });

  it('says no L1 yet when lastPriceTs is 0, even in compact GlobalAppBar', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={null}
          lastPriceTs={0}
          pricesStale={false}
          historyDate={null}
          compact
        />,
      );
    });
    const prices = container.querySelector('[data-testid="status-chip-prices"]');
    expect(prices?.textContent).toMatch(/no L1 yet/);
    expect(prices?.className).toMatch(/warn/);
  });

  it('renders feed_error / subscriptionError as one Roster chip', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={3}
          lastPriceTs={100}
          honestyText="L1 capacity"
          historyDate={null}
          compact
        />,
      );
    });
    const chip = container.querySelector('[data-testid="status-chip-honesty"]');
    expect(chip?.textContent).toMatch(/Roster/);
    expect(chip?.textContent).toMatch(/L1 capacity/);
  });

  it('shows Reload backend when API is up and local restart is available', () => {
    act(() => {
      root.render(
        <HeaderConnectionStatus
          health={healthy}
          discoveryProvider="ibkr"
          ibkrConnected
          activeFeed="sip"
          feedFellBack={false}
          secondsAgo={12}
          historyDate={null}
        />,
      );
    });

    expect(container.textContent).toMatch(/Reload backend/);
  });
});
