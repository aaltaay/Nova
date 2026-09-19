/**
 * @vitest-environment jsdom
 *
 * Intentional Paper<->Live Gateway switch -- real POST to
 * /api/ibkr/gateway-mode via novaFetch (X-Nova-Api-Key), honest error
 * surfacing, never arms live spend.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';

const refreshIbkrStatusNow = vi.fn();
const confirmAppMock = vi.fn();

vi.mock('./useIbkrStatus', () => ({
  refreshIbkrStatusNow: () => refreshIbkrStatusNow(),
}));

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

import { GatewayModeCapsule } from './GatewayModeCapsule';

describe('GatewayModeCapsule — intentional Gateway switch', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    refreshIbkrStatusNow.mockClear();
    confirmAppMock.mockReset();
    confirmAppMock.mockResolvedValue(true);
    localStorage.clear();
    localStorage.setItem(NOVA_API_KEY_STORAGE, 'test-nova-key');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  function requestHeaders(init: RequestInit | undefined): Headers {
    return new Headers(init?.headers);
  }

  function render(
    mode: 'paper' | 'live' | 'disconnected',
    gatewayMode?: 'paper' | 'live',
  ) {
    act(() => {
      root.render(
        <GatewayModeCapsule
          mode={mode}
          gatewayMode={gatewayMode}
          errorTestId="gateway-mode-capsule-error"
        />,
      );
    });
  }

  function liveButton() {
    return container.querySelectorAll('.sv-capsule__seg')[1] as HTMLButtonElement;
  }

  function simButton() {
    return container.querySelectorAll('.sv-capsule__seg')[2] as HTMLButtonElement;
  }

  it('clicking Sim confirms and POSTs /api/sim enabled true', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ sim: true, broker: 'sim' }), { status: 200 }),
      );
    render('paper');

    await act(async () => {
      simButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(confirmAppMock).toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/sim'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ enabled: true }),
      }),
    );
    expect(requestHeaders(fetchSpy.mock.calls[0][1] as RequestInit).get(NOVA_API_KEY_HEADER)).toBe(
      'test-nova-key',
    );
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('clicking Live confirms, POSTs gateway-mode, and refreshes status on success', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true, mode: 'live', error: null }), { status: 200 }),
      );
    render('paper');

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(confirmAppMock).toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/ibkr/gateway-mode'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ mode: 'live' }),
      }),
    );
    const sentBody = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(sentBody).toEqual({ mode: 'live' });
    expect(requestHeaders(fetchSpy.mock.calls[0][1] as RequestInit).get(NOVA_API_KEY_HEADER)).toBe(
      'test-nova-key',
    );
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('does not call the API when the user cancels the confirm', async () => {
    confirmAppMock.mockResolvedValue(false);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render('paper');

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(confirmAppMock).toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('surfaces an honest inline error and stays off Live when the switch fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          error: 'Could not connect to the live Gateway on port 4001',
        }),
        { status: 200 },
      ),
    );
    render('paper');

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    const error = container.querySelector('[data-testid="gateway-mode-capsule-error"]');
    expect(error).toBeTruthy();
    expect(error!.textContent).toMatch(/Could not connect/);
    expect(liveButton().classList.contains('is-selected')).toBe(false);
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('surfaces an inline error when the backend is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));
    render('paper');

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    const error = container.querySelector('[data-testid="gateway-mode-capsule-error"]');
    expect(error).toBeTruthy();
    expect(error!.textContent).toMatch(/Could not reach Nova backend/);
  });

  it('keeps Paper/Live clickable when disconnected so operators can retarget the listening port', async () => {
    confirmAppMock.mockResolvedValue(false);
    render('disconnected', 'paper');
    const segs = container.querySelectorAll('.sv-capsule__seg');
    expect((segs[0] as HTMLButtonElement).disabled).toBe(false);
    expect((segs[1] as HTMLButtonElement).disabled).toBe(false);
    expect(segs[0].classList.contains('is-selected')).toBe(true);

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
    });
    expect(confirmAppMock).toHaveBeenCalled();
  });

  it('surfaces restart-API hint when gateway-mode returns 404 (stale uvicorn)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 }),
    );
    render('paper');

    await act(async () => {
      liveButton().click();
      await Promise.resolve();
      await Promise.resolve();
    });

    const error = container.querySelector('[data-testid="gateway-mode-capsule-error"]');
    expect(error).toBeTruthy();
    expect(error!.textContent).toMatch(/Restart Nova API/i);
  });

  it('hints at the Live segment when disconnect_hint is a port mismatch', () => {
    act(() => {
      root.render(
        <GatewayModeCapsule
          mode="disconnected"
          gatewayMode="paper"
          disconnectHint="paper_port_refused_live_listening"
        />,
      );
    });
    const hint = container.querySelector('[data-testid="gateway-mode-capsule-disconnect-hint"]');
    expect(hint).toBeTruthy();
    expect(hint!.textContent).toMatch(/switching to live/i);
    // Slim capsule: the Live segment is the switch; no separate CTA button.
    expect(container.querySelector('[data-testid="sv-disconnect-hint-cta"]')).toBeNull();
  });

  it('drops the disconnect hint once the hinted mode is selected', () => {
    act(() => {
      root.render(
        <GatewayModeCapsule
          mode="disconnected"
          gatewayMode="live"
          disconnectHint="paper_port_refused_live_listening"
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="gateway-mode-capsule-disconnect-hint"]'),
    ).toBeNull();
  });
});
