/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PhoneDoor, closingOrder, orderStamp, refusalText, type OrderContext } from './linkOrders';
import { blockedWhy, buyBlockedWhy } from './linkOrdersPanel';

const ctx = (over: Partial<OrderContext> = {}): OrderContext => ({
  symbol: 'F',
  offsetMs: -129,
  instance: 'f5842c72cc74',
  book: { seq: 41, at: 1_794_344_000.5, bid: 12.01, ask: 12.02 },
  ...over,
});

describe("an order's stamp", () => {
  it("puts the tap on the PC's clock, so a phone that runs ahead is not judged on its own time", () => {
    // The phone is 129 ms ahead of the PC: a tap at phone time T happened at PC time T - 129.
    const stamp = orderStamp(ctx(), 1_794_344_001_000, 5_000);
    expect(stamp?.view.action_wall_ms).toBe(1_794_344_000_871);
    expect(stamp?.client_timing.action_wall_ms).toBe(1_794_344_000_871);
    expect(stamp?.client_timing.action_performance_ms).toBe(5_000);
  });

  it('carries the Level 2 version this device last received and the backend it came from', () => {
    const stamp = orderStamp(ctx(), 1_000, 1);
    expect(stamp?.view).toMatchObject({ schema_version: 1, symbol: 'F', instance: 'f5842c72cc74', book: { seq: 41, bid: 12.01, ask: 12.02 } });
  });

  it('is not made before the clock is measured', () => {
    expect(orderStamp(ctx({ offsetMs: null }), 1_000, 1)).toBeNull();
  });
});

describe("Nova's words for a refusal", () => {
  it('reads the phone door, the request guard and the order door', () => {
    expect(refusalText(409, { detail: { reason: 'PHONE_LIVE_LOOK_ONLY', error: 'The desk is on Live: from the phone, Live is look only. Send Live orders from the PC. Nothing was sent.' } }))
      .toBe('The desk is on Live: from the phone, Live is look only. Send Live orders from the PC. Nothing was sent.');
    expect(refusalText(403, { detail: 'Nova is view-only from another device', reason: 'REMOTE_VIEW_ONLY' })).toBe('Nova is view-only from another device');
    expect(refusalText(200, { ok: false, error: 'Your Level 2 was 1.2 s behind', reason_code: 'VIEW_STALE' })).toBe('Your Level 2 was 1.2 s behind');
    expect(refusalText(422, { detail: [{ msg: 'Field required' }] })).toBe('Nova did not accept that order as written.');
    expect(refusalText(502, null)).toBe('Nova answered 502.');
  });
});

describe('what closes a position', () => {
  it('sells a long, buys back a short, and sends nothing when flat', () => {
    expect(closingOrder({ qty: 100, position_side: 'long' })).toEqual({ side: 'SELL', qty: 100 });
    expect(closingOrder({ qty: 50, position_side: 'short' })).toEqual({ side: 'BUY', qty: 50 });
    expect(closingOrder({ qty: -50 })).toEqual({ side: 'BUY', qty: 50 });
    expect(closingOrder({ qty: 0 })).toBeNull();
    expect(closingOrder(undefined)).toBeNull();
  });
});

describe('why the order buttons are off', () => {
  const status = { pin_set: true, unlocked: true, expires_at: null, venue: 'paper', paper: true, armed: true };

  it('names the one thing to do next, and nothing when orders may go', () => {
    expect(blockedWhy(null, true)).toBe('Nova could not be reached.');
    expect(blockedWhy({ ...status, pin_set: false }, true)).toContain('tools/set_phone_pin.py');
    expect(blockedWhy({ ...status, unlocked: false }, true)).toBe('Locked. Enter your phone PIN.');
    expect(blockedWhy({ ...status, venue: 'live', paper: false, trades: false }, true)).toContain('look only');
    // Sim trades from the phone: the door says so in `trades`.
    expect(blockedWhy({ ...status, venue: 'sim', paper: false, trades: true }, true)).toBeNull();
    expect(blockedWhy(status, false)).toContain('Press Start');
    expect(blockedWhy(status, true)).toBeNull();
  });

  it('holds Buy alone until this device has the clock and a Level 2 book', () => {
    expect(buyBlockedWhy(ctx())).toBeNull();
    expect(buyBlockedWhy(ctx({ book: null }))).toContain('No Level 2 received for F');
    expect(buyBlockedWhy(ctx({ instance: null }))).toContain('Sell, Flatten and Cancel still work');
    expect(buyBlockedWhy(ctx({ offsetMs: null }))).toContain('clock');
    expect(buyBlockedWhy(null)).toBeNull();
  });
});

describe("the door, as the phone's screens use it", () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = (status: number, body: unknown) =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  const STATUS = { schema_version: 1, pin_set: true, unlocked: true, expires_at: 99, venue: 'paper', paper: true, armed: false, now: 1_794_400_000 };

  it('reads the status with its session, timed, and holds no session before an unlock', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, STATUS));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    expect(door.hasSession()).toBe(false);
    const beat = await door.beat();
    expect(beat.status).toMatchObject({ venue: 'paper', now: 1_794_400_000 });
    expect(beat.ms).toBeGreaterThanOrEqual(0);
    expect(fetchMock.mock.calls[0][0]).toBe('https://pc.test:8443/api/phone');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('GET');

    fetchMock.mockImplementationOnce(() => answer(200, { ...STATUS, token: 'tok-1' }));
    expect((await door.unlock('123456')).ok).toBe(true);
    expect(door.hasSession()).toBe(true);
    await door.beat();
    const headers = fetchMock.mock.calls[2][1]?.headers as Record<string, string>;
    expect(headers['X-Nova-Phone-Session']).toBe('tok-1');
  });

  it('answers "no status" when Nova cannot be reached, and drops a session the backend no longer accepts', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    const door = new PhoneDoor('https://pc.test:8443');
    expect((await door.beat()).status).toBeNull();

    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, { ...STATUS, token: 'tok-2' }));
    vi.stubGlobal('fetch', fetchMock);
    await door.unlock('123456');
    fetchMock.mockImplementationOnce(() => answer(401, { detail: { reason: 'PHONE_LOCKED', error: 'Unlock with your phone PIN first. Nothing was sent.' } }));
    expect((await door.beat()).status).toBeNull();
    expect(door.hasSession()).toBe(false);
  });

  it('drops its session when the status says it ended: 8 hours, a backend restart, or a newer unlock', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, { ...STATUS, token: 'tok-3' }));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    await door.unlock('123456');
    await door.beat();
    expect(door.hasSession()).toBe(true);
    // The status still answers 200; it only stops saying the session is good.
    fetchMock.mockImplementationOnce(() => answer(200, { ...STATUS, unlocked: false, expires_at: null }));
    expect((await door.beat()).status).toMatchObject({ unlocked: false });
    expect(door.hasSession()).toBe(false);
  });

  it('keeps a fresh session when a read that left before the unlock comes back saying "locked"', async () => {
    let release!: (r: Response) => void;
    const slow = new Promise<Response>((resolve) => { release = resolve; });
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, { ...STATUS, token: 'tok-4' }));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    // A heartbeat goes out with no token, and is still in the air when the PIN is accepted.
    fetchMock.mockImplementationOnce(() => slow);
    const early = door.beat();
    await door.unlock('123456');
    release(new Response(JSON.stringify({ ...STATUS, unlocked: false, expires_at: null }), { status: 200 }));
    await early;
    expect(door.hasSession()).toBe(true);
  });

  it("cancels one working order by its id, and says the refusal in the door's words", async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, { ok: true, order_id: 41 }));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    const done = await door.cancelOrder(41, 'ABCD Sell 250');
    expect(done).toMatchObject({ ok: true, text: 'Cancelled: ABCD Sell 250.' });
    expect(fetchMock.mock.calls[0][0]).toBe('https://pc.test:8443/api/phone/order/41');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');

    fetchMock.mockImplementationOnce(() => answer(409, { detail: { reason: 'PHONE_LIVE_LOOK_ONLY', error: 'The desk is on Live: from the phone, Live is look only. Send Live orders from the PC. Nothing was sent.' } }));
    expect(await door.cancelOrder(41, 'ABCD Sell 250')).toMatchObject({ ok: false, text: 'The desk is on Live: from the phone, Live is look only. Send Live orders from the PC. Nothing was sent.' });
  });

  it("moves the desk's venue through the door and says what the desk cancelled", async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, {
      pin_set: true, unlocked: true, expires_at: null, venue: 'sim', paper: false, trades: true, armed: false,
      left: [{ venue: 'paper', symbol: 'F', order_id: 7 }], gateway: null,
    }));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    const moved = await door.moveVenue('sim');
    expect(fetchMock.mock.calls[0][0]).toBe('https://pc.test:8443/api/phone/venue');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ venue: 'sim' });
    expect(moved).toMatchObject({ ok: true, text: 'Switched to Sim. The desk switched too. Cancelled 1 working order on the venue left.' });
    expect(moved.status?.venue).toBe('sim');
  });

  it('reads what a switch would cancel, and says nothing was read when Nova does not answer', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, {
      venue: 'paper', lines: ['The desk is armed on Paper: switching disarms it', 7], unknown: ['armed'],
    }));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    expect(await door.venueEffects()).toEqual({ venue: 'paper', lines: ['The desk is armed on Paper: switching disarms it'], unknown: ['armed'] });
    fetchMock.mockImplementationOnce(() => answer(503, null));
    expect(await door.venueEffects()).toBeNull();
  });

  it("steps the Sim's playhead and hands back the desk's new clock", async () => {
    const clock = { sim: true, paused: true, minute_from_open: 331 };
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => answer(200, clock));
    vi.stubGlobal('fetch', fetchMock);
    const door = new PhoneDoor('https://pc.test:8443');
    const moved = await door.simClock({ minute_from_open: 331, symbol: 'F' }, 'Back a minute');
    expect(fetchMock.mock.calls[0][0]).toBe('https://pc.test:8443/api/phone/sim/clock');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ minute_from_open: 331, symbol: 'F' });
    expect(moved).toMatchObject({ ok: true, text: 'Back a minute', clock });
  });
});
