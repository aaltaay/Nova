/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GatewayDisconnectedBannerHost } from './GatewayDisconnectedBannerHost';

vi.mock('../utils/launchIbGateway', () => ({
  launchIbGateway: vi.fn().mockResolvedValue({ ok: true, message: 'ok' }),
}));

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    ibkrConnected: false,
    ibkrTransportConnected: false,
    ibkrPortsDark: true,
    ibkrDisconnectHint: 'both_ports_unreachable',
    ibkrSecondFactorStale: false,
    ibkrGatewayMode: 'live',
  }),
}));

vi.mock('../settings/SettingsContext', () => ({
  useSettings: () => ({
    settings: { discoveryProvider: 'ibkr' },
  }),
}));

describe('GatewayDisconnectedBannerHost', () => {
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

  it('renders Open live Gateway when Trader would hide DashboardPage', () => {
    act(() => {
      root.render(<GatewayDisconnectedBannerHost />);
    });
    const banner = container.querySelector('[data-testid="gateway-disconnected-banner"]');
    expect(banner).not.toBeNull();
    expect(banner?.querySelector('[data-testid="open-gateway-live"]')?.textContent).toMatch(
      /live/i,
    );
  });
});
