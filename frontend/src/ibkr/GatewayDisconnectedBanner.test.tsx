/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GatewayDisconnectedBanner } from './GatewayDisconnectedBanner';

const launchIbGatewayMock = vi.fn();

vi.mock('../utils/launchIbGateway', () => ({
  launchIbGateway: (...args: unknown[]) => launchIbGatewayMock(...args),
}));

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
        <GatewayDisconnectedBanner discoveryProvider="alpaca" ibkrConnected={false} />,
      );
    });
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')).toBeNull();
  });

  it('renders nothing when IBKR is connected', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner discoveryProvider="ibkr" ibkrConnected={true} />,
      );
    });
    expect(container.querySelector('[data-testid="gateway-disconnected-banner"]')).toBeNull();
  });

  it('shows the loud banner with mode-aware copy when disconnected', () => {
    act(() => {
      root.render(
        <GatewayDisconnectedBanner
          discoveryProvider="ibkr"
          ibkrConnected={false}
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
        <GatewayDisconnectedBanner discoveryProvider="ibkr" ibkrConnected={false} />,
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
