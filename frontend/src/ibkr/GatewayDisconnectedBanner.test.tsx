/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GatewayDisconnectedBanner,
  shouldShowGatewayLoginBanner,
} from './GatewayDisconnectedBanner';

import { getRecordingSymbols } from '../capture/sessionRecordStore';
import {
  _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests,
  pollIbkrStatusOnce,
} from './ibkrStatusPoller';

const launchIbGatewayMock = vi.fn();

vi.mock('../utils/launchIbGateway', () => ({
  launchIbGateway: (...args: unknown[]) => launchIbGatewayMock(...args),
}));

describe('shouldShowGatewayLoginBanner', () => {
  it('hides when discovery is not ibkr', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'alpaca',
        ibkrConnected: false,
        ibkrTransportConnected: false,
      }),
    ).toBe(false);
  });

  it('hides when session is usable', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: true,
        ibkrTransportConnected: true,
      }),
    ).toBe(false);
  });

  it('hides when transport is up but session not usable (Error 1100)', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: true,
      }),
    ).toBe(false);
  });

  it('hides when the other Gateway port is already up (not a login)', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: false,
        ibkrDisconnectHint: 'live_port_refused_paper_listening',
      }),
    ).toBe(false);
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: false,
        ibkrDisconnectHint: 'paper_port_refused_live_listening',
      }),
    ).toBe(false);
  });

  it('hides when Gateway API port is open but Nova session is not READY', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: false,
        ibkrDisconnectHint: 'live_port_open_but_disconnected',
      }),
    ).toBe(false);
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: false,
        ibkrDisconnectHint: 'paper_port_open_but_disconnected',
      }),
    ).toBe(false);
  });

  it('hides when status fields are missing (API probe miss)', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
      }),
    ).toBe(false);
  });

  it('shows when transport is down', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrTransportConnected: false,
      }),
    ).toBe(true);
  });

  it('shows when ports are dark even without transport field', () => {
    expect(
      shouldShowGatewayLoginBanner({
        discoveryProvider: 'ibkr',
        ibkrConnected: false,
        ibkrPortsDark: true,
      }),
    ).toBe(true);
  });
});

describe('GatewayDisconnectedBanner', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    launchIbGatewayMock.mockReset();
    _resetIbkrStatusPollerForTests();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    _resetIbkrStatusPollerForTests();
  });

  it('keeps the Gateway alarm visible with real fresh and failed recording state (#316)', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const banner = () => container.querySelector('[data-testid="gateway-disconnected-banner"]');
    act(() => {
      root.render(
        <GatewayDisconnectedBanner discoveryProvider="ibkr" ibkrConnected={false} ibkrTransportConnected={false} />,
      );
    });
    expect(banner()).not.toBeNull();
    _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ capture: true, recording: true, capture_symbol: 'IMCC' }),
    }));
    await pollIbkrStatusOnce();
    expect(getRecordingSymbols()).toEqual(['IMCC']);
    expect(banner()).not.toBeNull();
    _setIbkrStatusPollerFetchForTests(vi.fn().mockRejectedValue(new Error('backend down')));
    await pollIbkrStatusOnce();
    expect(getRecordingSymbols()).toEqual([]);
    expect(banner()).not.toBeNull();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('renders nothing when discoveryProvider is not ibkr', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="alpaca"
          ibkrConnected={false}
          ibkrTransportConnected={false}
        />,
      );
    });
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')).toBeNull();
  });

  it('renders nothing when IBKR session is usable', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={true}
          ibkrTransportConnected={true}
        />,
      );
    });
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')).toBeNull();
  });

  it('renders nothing when transport is up but session not usable', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={false}
          ibkrTransportConnected={true}
        />,
      );
    });
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')).toBeNull();
  });

  it('shows the loud banner with mode-aware copy when Gateway transport is down', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={false}
          ibkrTransportConnected={false}
          ibkrGatewayMode="paper"
        />,
      );
    });
    const banner = container.querySelector('[data-testid="gateway-disconnected-banner"]');
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain('ACTION REQUIRED');
    expect(banner?.textContent).toContain('4002');
    expect(banner?.querySelector('[data-testid="open-gateway-paper"]')?.textContent).toMatch(/paper/i);
    expect(banner?.querySelector('[data-testid="open-gateway-live"]')?.textContent).toMatch(/live/i);
  });

  it('calls launchIbGateway when the CTA is clicked', async () => {
    launchIbGatewayMock.mockResolvedValue({ ok: true, message: 'Started IB Gateway' });
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={false}
          ibkrTransportConnected={false}
        />,
      );
    });
    const button = container.querySelector('[data-testid="open-gateway-paper"]') as HTMLButtonElement;
    await act(async () => {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(launchIbGatewayMock).toHaveBeenCalledWith('paper', false);
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')?.textContent).toContain(
      'Started IB Gateway',
    );

    const live = container.querySelector('[data-testid="open-gateway-live"]') as HTMLButtonElement;
    await act(async () => {
      live.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(launchIbGatewayMock).toHaveBeenCalledWith('live', false);
  });

  it('forces a fresh login instead of just focusing a stale Second Factor prompt', async () => {
    launchIbGatewayMock.mockResolvedValue({ ok: true, message: 'Started IB Gateway' });
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={false}
          ibkrTransportConnected={false}
          ibkrSecondFactorStale
        />,
      );
    });
    const banner = container.querySelector('[data-testid="gateway-disconnected-banner"]');
    expect(banner?.textContent).toContain('expired');
    const live = container.querySelector('[data-testid="open-gateway-live"]') as HTMLButtonElement;
    await act(async () => {
      live.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(launchIbGatewayMock).toHaveBeenCalledWith('live', true);
  });
});
