/**
 * @vitest-environment jsdom
 *
 * The one unlock flow: Paper / Sim arm in one call with no dialog; Live opens
 * the PIN dialog, sends the digits to POST /api/ibkr/arm and shows the
 * backend's refusal in its own words. A fake backend holds the latch.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY, TICKER_TRADE_LIVE_PIN_NOT_SET } from '../constants';
import { _resetIbkrStatusPollerForTests, subscribeIbkrStatus } from './ibkrStatusPoller';
import { readTicketSessionUnlocked } from './ticketUnlock';
import { useTradingPinGate } from './useTradingPinGate';

// input-otp needs layout APIs jsdom lacks; a plain input drives the same onChange.
vi.mock('@/components/ui/input-otp', () => ({
  InputOTP: ({ value, disabled, onChange }: {
    value: string; disabled?: boolean; onChange: (next: string) => void;
  }) => (
    <input
      data-testid="pin-input"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
  InputOTPGroup: () => null,
  InputOTPSlot: () => null,
}));

const alertApp = vi.hoisted(() => vi.fn(async () => {}));
vi.mock('../ux', () => ({ alertApp }));

type ArmAnswer = { status: number; body: unknown };

function fakeBackend(start: Record<string, unknown>) {
  const server: Record<string, unknown> = { connected: true, mode: 'live', armed: false, ...start };
  const posts: Record<string, unknown>[] = [];
  const answers: ArmAnswer[] = [];
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url).endsWith('/api/ibkr/arm')) {
      const body = JSON.parse(String(init?.body));
      posts.push(body);
      const next = answers.shift() ?? { status: 200, body: {} };
      if (next.status === 200) server.armed = body.armed;
      return { ok: next.status === 200, status: next.status, json: async () => next.body } as Response;
    }
    return { ok: true, status: 200, json: async () => ({ ...server }) } as Response;
  });
  return { server, posts, answers, fetchMock };
}

function Harness({ onResult }: { onResult: (ok: boolean) => void }) {
  const { ensureUnlocked, pinDialog } = useTradingPinGate();
  return (
    <>
      <button type="button" onClick={() => void ensureUnlocked().then(onResult)}>place</button>
      {pinDialog}
    </>
  );
}

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
}

let offStatus: () => void = () => {};

async function startDesk(start: Record<string, unknown>) {
  const backend = fakeBackend(start);
  vi.stubGlobal('fetch', backend.fetchMock);
  offStatus = subscribeIbkrStatus(() => {});
  await vi.waitFor(() => expect(backend.fetchMock).toHaveBeenCalled());
  await act(flush);
  return backend;
}

describe('useTradingPinGate', () => {
  beforeEach(() => {
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    _resetIbkrStatusPollerForTests();
    alertApp.mockClear();
  });

  afterEach(() => {
    cleanup();
    offStatus();
    _resetIbkrStatusPollerForTests();
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    vi.unstubAllGlobals();
  });

  it.each(['paper', 'sim'])('%s: one click arms the desk, no PIN dialog', async (venue) => {
    const backend = await startDesk({ mode: venue, venue, arm_requires_pin: false });
    const onResult = vi.fn();
    render(<Harness onResult={onResult} />);

    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(backend.posts).toEqual([{ armed: true, actor: 'operator' }]);
    expect(onResult).toHaveBeenCalledWith(true);
    await vi.waitFor(() => expect(readTicketSessionUnlocked()).toBe(true));
  });

  it("Paper: a refused one-click arm resolves false and says the backend's reason", async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const backend = await startDesk({ mode: 'paper', venue: 'paper', arm_requires_pin: false });
    backend.answers.push({ status: 409, body: { detail: 'Orders are off in .env', code: 'SPEND_OFF' } });
    const onResult = vi.fn();
    render(<Harness onResult={onResult} />);

    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });

    expect(onResult).toHaveBeenCalledWith(false);
    expect(alertApp).toHaveBeenCalledWith(expect.objectContaining({ message: 'Orders are off in .env' }));
    expect(readTicketSessionUnlocked()).toBe(false);
    warn.mockRestore();
  });

  it("Live: the PIN goes to the backend; a 403 shows its detail, a 200 unlocks", async () => {
    const backend = await startDesk({ mode: 'live', venue: 'live', arm_requires_pin: true, live_arm_pin_set: true });
    backend.answers.push({ status: 403, body: { detail: 'Wrong PIN', code: 'ARM_PIN_INVALID' } });
    const onResult = vi.fn();
    render(<Harness onResult={onResult} />);

    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(backend.posts).toEqual([]);

    await act(async () => {
      fireEvent.change(screen.getByTestId('pin-input'), { target: { value: '000000' } });
      await flush();
    });
    expect(backend.posts).toEqual([{ armed: true, actor: 'operator', pin: '000000' }]);
    expect(screen.getByTestId('trading-pin-error').textContent).toBe('Wrong PIN');
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(onResult).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.change(screen.getByTestId('pin-input'), { target: { value: '135790' } });
      await flush();
    });
    expect(backend.posts.at(-1)).toEqual({ armed: true, actor: 'operator', pin: '135790' });
    expect(onResult).toHaveBeenCalledWith(true);
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await vi.waitFor(() => expect(readTicketSessionUnlocked()).toBe(true));
  });

  it('Live: an unreported arm_requires_pin (older API) asks for the PIN', async () => {
    await startDesk({ mode: 'live' });
    render(<Harness onResult={vi.fn()} />);
    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('Live with no PIN set: the dialog says how to set one before anything is typed', async () => {
    await startDesk({ mode: 'live', venue: 'live', arm_requires_pin: true, live_arm_pin_set: false });
    render(<Harness onResult={vi.fn()} />);
    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });
    expect(screen.getByTestId('trading-pin-error').textContent).toBe(TICKER_TRADE_LIVE_PIN_NOT_SET);
  });

  it('Cancel resolves false and sends nothing', async () => {
    const backend = await startDesk({ mode: 'live', venue: 'live', arm_requires_pin: true });
    const onResult = vi.fn();
    render(<Harness onResult={onResult} />);
    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });
    await act(async () => { fireEvent.click(screen.getByText('Cancel')); await flush(); });
    expect(onResult).toHaveBeenCalledWith(false);
    expect(backend.posts).toEqual([]);
  });

  it('already armed: resolves true without a request', async () => {
    const backend = await startDesk({ mode: 'live', venue: 'live', armed: true, arm_requires_pin: true });
    const onResult = vi.fn();
    render(<Harness onResult={onResult} />);
    await act(async () => { fireEvent.click(screen.getByText('place')); await flush(); });
    expect(onResult).toHaveBeenCalledWith(true);
    expect(backend.posts).toEqual([]);
  });
});
