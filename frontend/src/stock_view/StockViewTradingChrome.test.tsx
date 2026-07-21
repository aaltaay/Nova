/**
 * @vitest-environment jsdom
 *
 * Intentional Paper<->Live Gateway switch capsule — real POST to
 * /api/ibkr/gateway-mode, honest error surfacing, never arms live spend.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const refreshIbkrStatusNow = vi.fn();
const confirmAppMock = vi.fn();

vi.mock('../ibkr/useIbkrStatus', () => ({
  refreshIbkrStatusNow: () => refreshIbkrStatusNow(),
}));

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

import { StockViewAccountModeCapsule } from './StockViewTradingChrome';

describe('StockViewAccountModeCapsule — intentional Gateway switch', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    refreshIbkrStatusNow.mockClear();
    confirmAppMock.mockReset();
    confirmAppMock.mockResolvedValue(true);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  function render(
    mode: 'paper' | 'live' | 'disconnected',
    gatewayMode?: 'paper' | 'live',
  ) {
    act(() => {
      root.render(
        <div className="stock-view-page">
          <StockViewAccountModeCapsule mode={mode} gatewayMode={gatewayMode} />
        </div>,
      );
    });
  }

  function liveButton() {
    return container.querySelectorAll('.sv-capsule__seg')[1] as HTMLButtonElement;
  }

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

    const error = container.querySelector('[data-testid="sv-account-mode-error"]');
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

    const error = container.querySelector('[data-testid="sv-account-mode-error"]');
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

    const error = container.querySelector('[data-testid="sv-account-mode-error"]');
    expect(error).toBeTruthy();
    expect(error!.textContent).toMatch(/Restart Nova API/i);
  });

  it('shows a one-click Switch CTA when disconnect_hint is a port mismatch', () => {
    act(() => {
      root.render(
        <div className="stock-view-page">
          <StockViewAccountModeCapsule
            mode="disconnected"
            gatewayMode="paper"
            disconnectHint="paper_port_refused_live_listening"
          />
        </div>,
      );
    });
    const cta = container.querySelector('[data-testid="sv-disconnect-hint-cta"]');
    expect(cta).toBeTruthy();
    expect(cta!.textContent).toMatch(/Switch to Live/i);
  });
});
