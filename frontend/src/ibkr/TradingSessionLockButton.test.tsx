/**
 * @vitest-environment jsdom
 *
 * The header padlock is the backend arm latch (ADR 018): it reads
 * /api/ibkr/status.armed and moves it with POST /api/ibkr/arm. A fake backend
 * holds the latch; nothing about the padlock lives in the tab.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  IBKR_STATUS_SESSION_KEY,
  TICKER_TRADE_LOCK_ICON_LOCKED_NO_PIN_TITLE,
  TICKER_TRADE_LOCK_ICON_PIN_NOT_SET_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_BY_BOT_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE,
} from '../constants';
import { _resetIbkrStatusPollerForTests, refreshIbkrStatusNow } from './ibkrStatusPoller';
import { TradingSessionLockButton } from './TradingSessionLockButton';

vi.mock('./TradingPinDialog', () => ({
  TradingPinDialog: ({ open }: { open: boolean }) => (open ? <div role="dialog">PIN</div> : null),
}));

function fakeBackend(start: Record<string, unknown>) {
  const server: Record<string, unknown> = {
    connected: true, mode: 'paper', venue: 'paper', spend_status: 'paper_armed', armed: false, ...start,
  };
  const posts: Record<string, unknown>[] = [];
  const status = () => ({
    ...server,
    trading_allowed: server.blocked ? false : server.armed === true,
    trading_allowed_reason: server.blocked ?? (server.armed ? null : 'Desk is disarmed'),
    armed_by: server.armed ? server.armed_by ?? 'operator' : null,
  });
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url).endsWith('/api/ibkr/arm')) {
      const body = JSON.parse(String(init?.body));
      posts.push(body);
      server.armed = body.armed;
      return { ok: true, status: 200, json: async () => status() } as Response;
    }
    return { ok: true, status: 200, json: async () => status() } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return { server, posts, fetchMock };
}

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
}

async function renderPadlocks(count = 1) {
  await act(async () => {
    render(
      <>
        {Array.from({ length: count }, (_, i) => <TradingSessionLockButton key={i} />)}
      </>,
    );
    await flush();
  });
  return screen.getAllByTestId('global-bar-trade-lock') as HTMLButtonElement[];
}

describe('TradingSessionLockButton', () => {
  beforeEach(() => {
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    _resetIbkrStatusPollerForTests();
  });

  afterEach(() => {
    cleanup();
    _resetIbkrStatusPollerForTests();
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    vi.unstubAllGlobals();
  });

  it('Paper: one click arms the desk and the padlock opens', async () => {
    const backend = fakeBackend({ arm_requires_pin: false });
    const [btn] = await renderPadlocks();
    // The backend's own reason follows the title.
    await vi.waitFor(() => expect(btn.title).toBe(`${TICKER_TRADE_LOCK_ICON_LOCKED_NO_PIN_TITLE} Desk is disarmed`));
    expect(btn.className).toMatch(/is-locked/);

    await act(async () => { fireEvent.click(btn); await flush(); });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(backend.posts).toEqual([{ armed: true, actor: 'operator' }]);
    await vi.waitFor(() => expect(btn.className).toMatch(/is-unlocked/));
    expect(btn.title).toBe(TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE);
  });

  it('Live: a click while locked opens the PIN dialog and sends nothing yet', async () => {
    const backend = fakeBackend({ mode: 'live', venue: 'live', arm_requires_pin: true, live_arm_pin_set: true });
    const [btn] = await renderPadlocks();
    await vi.waitFor(() => expect(backend.fetchMock).toHaveBeenCalled());
    await act(async () => { fireEvent.click(btn); await flush(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(backend.posts).toEqual([]);
  });

  it('a click while armed posts {armed: false} and the padlock locks', async () => {
    const backend = fakeBackend({ armed: true, arm_requires_pin: true });
    const [btn] = await renderPadlocks();
    await vi.waitFor(() => expect(btn.className).toMatch(/is-unlocked/));

    await act(async () => { fireEvent.click(btn); await flush(); });

    expect(backend.posts).toEqual([{ armed: false, actor: 'operator' }]);
    await vi.waitFor(() => expect(btn.className).toMatch(/is-locked/));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('two padlocks cannot disagree: a disarm elsewhere locks both on the next read', async () => {
    const backend = fakeBackend({ armed: true, arm_requires_pin: false });
    const [a, b] = await renderPadlocks(2);
    await vi.waitFor(() => expect(a.className).toMatch(/is-unlocked/));
    expect(b.className).toMatch(/is-unlocked/);

    // Another window locked it, or the backend restarted: no click here.
    backend.server.armed = false;
    await act(async () => { refreshIbkrStatusNow(); await flush(); });

    await vi.waitFor(() => expect(a.className).toMatch(/is-locked/));
    expect(b.className).toMatch(/is-locked/);
  });

  it('says a bot unlocked it', async () => {
    fakeBackend({ armed: true, armed_by: 'bot', arm_requires_pin: false });
    const [btn] = await renderPadlocks();
    await vi.waitFor(() => expect(btn.title).toBe(TICKER_TRADE_LOCK_ICON_UNLOCKED_BY_BOT_TITLE));
  });

  it('Live with no PIN set: the title says how to set it', async () => {
    fakeBackend({ mode: 'live', venue: 'live', arm_requires_pin: true, live_arm_pin_set: false });
    const [btn] = await renderPadlocks();
    await vi.waitFor(() => expect(btn.title).toContain(TICKER_TRADE_LOCK_ICON_PIN_NOT_SET_TITLE));
    expect(btn.title).toMatch(/set_live_arm_pin\.py/);
  });

  it('armed but blocked by the backend: looks locked, says why, and the click locks', async () => {
    const backend = fakeBackend({ armed: true, arm_requires_pin: false, blocked: 'Orders locked -- IBKR_ORDERS_ENABLED is off' });
    const [btn] = await renderPadlocks();
    await vi.waitFor(() => expect(btn.title).toMatch(/ORDERS_ENABLED/));
    expect(btn.className).toMatch(/is-locked/);
    await act(async () => { fireEvent.click(btn); await flush(); });
    expect(backend.posts).toEqual([{ armed: false, actor: 'operator' }]);
  });
});
