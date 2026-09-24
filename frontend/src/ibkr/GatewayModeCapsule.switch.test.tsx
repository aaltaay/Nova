/**
 * @vitest-environment jsdom
 *
 * ADR 020 venue pills -- every pill POSTs /api/desk/venue via novaFetch
 * (X-Nova-Api-Key). Paper never launches a Gateway; Live also ensures the live
 * Gateway through /api/ibkr/gateway-mode; Sim falls back to POST /api/sim when
 * the venue route is missing. Honest error surfacing, never arms live spend.
 * One click switches: no confirm dialog (operator ask, 2026-09-23) -- the
 * global bar's venue tint says where the desk is, and Live still arms only
 * with the PIN (ADR 018).
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';

const refreshIbkrStatusNow = vi.fn();
const confirmAppMock = vi.fn();

const statusVenue: { venue?: 'live' | 'paper' | 'sim'; mode: string } = { mode: 'disconnected' };

vi.mock('./useIbkrStatus', () => ({
  refreshIbkrStatusNow: () => refreshIbkrStatusNow(),
  useIbkrStatus: () => statusVenue,
}));

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

import { GatewayModeCapsule } from './GatewayModeCapsule';

type Route = (url: string, init?: RequestInit) => Response | Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('GatewayModeCapsule — venue switch', () => {
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

  function mockFetch(route: Route) {
    return vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => Promise.resolve(route(String(input), init)));
  }

  function calledPaths(spy: ReturnType<typeof mockFetch>): string[] {
    return spy.mock.calls.map(call => new URL(String(call[0]), 'http://x').pathname);
  }

  function sentBody(spy: ReturnType<typeof mockFetch>, index: number): unknown {
    return JSON.parse((spy.mock.calls[index][1] as RequestInit).body as string);
  }

  function render(
    mode: 'paper' | 'live' | 'sim' | 'disconnected',
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

  function seg(index: 0 | 1 | 2) {
    return container.querySelectorAll('.sv-capsule__seg')[index] as HTMLButtonElement;
  }

  async function click(index: 0 | 1 | 2) {
    await act(async () => {
      seg(index).click();
      for (let i = 0; i < 6; i += 1) await Promise.resolve();
    });
  }

  function errorText(): string | null {
    return container.querySelector('[data-testid="gateway-mode-capsule-error"]')?.textContent ?? null;
  }

  it('Paper POSTs /api/desk/venue only -- no Gateway launch, no IBC, no /api/sim', async () => {
    const fetchSpy = mockFetch(() => json({ venue: 'paper' }));
    render('live');

    await click(0);

    expect(calledPaths(fetchSpy)).toEqual(['/api/desk/venue']);
    expect(sentBody(fetchSpy, 0)).toEqual({ venue: 'paper' });
    expect(new Headers((fetchSpy.mock.calls[0][1] as RequestInit).headers).get(NOVA_API_KEY_HEADER)).toBe(
      'test-nova-key',
    );
    expect(errorText()).toBeNull();
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('Live POSTs the venue, then ensures the live Gateway through gateway-mode', async () => {
    const fetchSpy = mockFetch(url =>
      url.includes('/api/desk/venue')
        ? json({ venue: 'live' })
        : json({ ok: true, mode: 'live', error: null, launch_action: 'noop' }),
    );
    render('paper');

    await click(1);

    expect(calledPaths(fetchSpy)).toEqual(['/api/desk/venue', '/api/ibkr/gateway-mode']);
    expect(sentBody(fetchSpy, 0)).toEqual({ venue: 'live' });
    expect(sentBody(fetchSpy, 1)).toEqual({ mode: 'live' });
    expect(errorText()).toBeNull();
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('Live shows the IBC launch message when the live Gateway still has to start', async () => {
    mockFetch(url =>
      url.includes('/api/desk/venue')
        ? json({ venue: 'live' })
        : json({ ok: true, launch_action: 'launch', message: 'Starting live Gateway -- approve 2FA' }),
    );
    render('paper');
    await click(1);
    expect(errorText()).toMatch(/approve 2FA/);
  });

  it('Sim POSTs the venue and never touches /api/sim when the route exists', async () => {
    const fetchSpy = mockFetch(() => json({ venue: 'sim' }));
    render('paper');

    await click(2);

    expect(calledPaths(fetchSpy)).toEqual(['/api/desk/venue']);
    expect(sentBody(fetchSpy, 0)).toEqual({ venue: 'sim' });
    expect(errorText()).toBeNull();
  });

  it('Sim falls back to POST /api/sim {enabled:true} when the venue route answers 404', async () => {
    const fetchSpy = mockFetch(url =>
      url.includes('/api/desk/venue')
        ? json({ detail: 'Not Found' }, 404)
        : json({ sim: true, broker: 'sim' }),
    );
    render('paper');

    await click(2);

    expect(calledPaths(fetchSpy)).toEqual(['/api/desk/venue', '/api/sim']);
    expect(sentBody(fetchSpy, 1)).toEqual({ enabled: true });
    expect(errorText()).toBeNull();
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('Paper on a stale API surfaces the restart hint instead of launching anything', async () => {
    const fetchSpy = mockFetch(() => json({ detail: 'Not Found' }, 404));
    render('live');
    await click(0);
    expect(calledPaths(fetchSpy)).toEqual(['/api/desk/venue']);
    expect(errorText()).toMatch(/Restart Nova API/i);
  });

  it('switches on one click: no confirm dialog for any venue, Live included', async () => {
    const fetchSpy = mockFetch(url =>
      url.includes('/api/desk/venue')
        ? json({ venue: JSON.parse(String(fetchSpy.mock.calls.at(-1)?.[1]?.body ?? '{}')).venue })
        : json({ ok: true, mode: 'live', error: null, launch_action: 'noop' }),
    );
    render('paper');
    await click(1);
    render('live');
    await click(2);
    render('sim');
    await click(0);
    expect(confirmAppMock).not.toHaveBeenCalled();
    expect(calledPaths(fetchSpy).filter(path => path === '/api/desk/venue')).toHaveLength(3);
    expect([0, 2, 3].map(i => sentBody(fetchSpy, i))).toEqual([
      { venue: 'live' },
      { venue: 'sim' },
      { venue: 'paper' },
    ]);
  });

  it('surfaces an honest inline error and stays off Live when the Gateway switch fails', async () => {
    mockFetch(url =>
      url.includes('/api/desk/venue')
        ? json({ venue: 'live' })
        : json({ ok: false, error: 'Could not connect to the live Gateway on port 4001' }),
    );
    render('paper');

    await click(1);

    expect(errorText()).toMatch(/Could not connect/);
    expect(seg(1).classList.contains('is-selected')).toBe(false);
    expect(refreshIbkrStatusNow).toHaveBeenCalled();
  });

  it('surfaces the backend error when the venue route refuses', async () => {
    mockFetch(() => json({ detail: 'venue store refused: unknown schema_version' }, 409));
    render('paper');
    await click(1);
    expect(errorText()).toMatch(/unknown schema_version/);
  });

  it('surfaces an inline error when the backend is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));
    render('paper');
    await click(1);
    expect(errorText()).toMatch(/Could not reach Nova backend/);
  });

  it('keeps every pill clickable when disconnected so operators can retarget', async () => {
    const fetchSpy = mockFetch(() => json({ detail: 'Not Found' }, 404));
    render('disconnected', 'paper');
    expect(seg(0).disabled).toBe(false);
    expect(seg(1).disabled).toBe(false);
    expect(seg(2).disabled).toBe(false);
    expect(seg(0).classList.contains('is-selected')).toBe(true);
    await click(1);
    expect(sentBody(fetchSpy, 0)).toEqual({ venue: 'live' });
  });

  it('tooltips say what each venue is', () => {
    render('paper');
    expect(seg(0).title).toMatch(/Nova's practice account/);
    expect(seg(0).title).toMatch(/fake money/i);
    expect(seg(1).title).toMatch(/IBKR, real money/);
    expect(seg(2).title).toMatch(/replay playground/);
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
    expect(container.querySelector('[data-testid="sv-disconnect-hint-cta"]')).toBeNull();
  });

  it('on the sample desk switches nothing: no confirm, no request, the refusal said (V4)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    window.history.replaceState({}, '', '/?view=sample');
    try {
      render('paper');
      await click(1);
      expect(confirmAppMock).not.toHaveBeenCalled();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(errorText()).toMatch(/Sample desk — venue switching is off/);
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });

  it('follows the status venue over a Gateway-label mode: Live on the paper Gateway is Live (C26)', () => {
    statusVenue.venue = 'live';
    statusVenue.mode = 'paper';
    try {
      render('paper', 'paper');
      expect(seg(1).classList.contains('is-selected')).toBe(true);
      expect(seg(0).classList.contains('is-selected')).toBe(false);
    } finally {
      delete statusVenue.venue;
      statusVenue.mode = 'disconnected';
    }
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
