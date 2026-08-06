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
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
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
    const button = container.querySelector('button') as HTMLButtonElement;
    await act(async () => {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(launchIbGatewayMock).toHaveBeenCalledOnce();
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')?.textContent).toContain(
      'Started IB Gateway',
    );
  });
});
