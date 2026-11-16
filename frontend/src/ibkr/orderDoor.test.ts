import { afterEach, describe, expect, it, vi } from 'vitest';
import { resetViewRegistryForTests } from '../market_view/viewRegistry';
import { noteBeat, noteBookFrame, noteBookShown, noteSubscribed, viewLockReason, viewStampFor } from '../market_view';
import { deskNow, setDeskClockOffsetMs } from '../utils/deskClock';
import { orderDoor, setOrderDoor } from './orderDoor';
import { cancelAllOrdersForSymbol, cancelAllWorkingOrders, placeIbkrOrder } from './placeOrder';

function answering(body: unknown) {
  const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  setOrderDoor(null);
  setDeskClockOffsetMs(0);
  resetViewRegistryForTests();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('the page\'s order door', () => {
  it('is the desk\'s unless the page installs another', async () => {
    expect(orderDoor().prefix).toBe('/api/ibkr');
    const fetchMock = answering({ ok: true, order_id: 7 });
    await placeIbkrOrder({ symbol: 'ABCD', side: 'BUY', qty: 1, order_type: 'MKT', outside_rth: false });
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/ibkr\/order$/);
  });

  it('sends an order and both cancels through the phone\'s door, with its session', async () => {
    setOrderDoor({ prefix: '/api/phone', headers: () => ({ 'X-Nova-Phone-Session': 'tok' }) });
    const fetchMock = answering({ ok: true, order_id: 7, cancelled: [], failed: [], error: null });
    await placeIbkrOrder({ symbol: 'ABCD', side: 'BUY', qty: 1, order_type: 'MKT', outside_rth: false });
    await cancelAllOrdersForSymbol('abcd');
    await cancelAllWorkingOrders();
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toMatch(/\/api\/phone\/order$/);
    expect(urls[1]).toMatch(/\/api\/phone\/orders\?symbol=ABCD$/);
    expect(urls[2]).toMatch(/\/api\/phone\/orders\?all_symbols=true$/);
    for (const call of fetchMock.mock.calls) {
      expect(new Headers(call[1]?.headers).get('X-Nova-Phone-Session')).toBe('tok');
    }
    // A cancel still carries when it was tapped.
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('X-Nova-Action-Wall-Ms')).not.toBeNull();
  });

  it('reads the door\'s headers when the order leaves, not when the door was installed', async () => {
    let token = 'first';
    setOrderDoor({ prefix: '/api/phone', headers: () => ({ 'X-Nova-Phone-Session': token }) });
    const fetchMock = answering({ ok: true, order_id: 7 });
    token = 'second';
    await placeIbkrOrder({ symbol: 'ABCD', side: 'BUY', qty: 1, order_type: 'MKT', outside_rth: false });
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-Nova-Phone-Session')).toBe('second');
  });
});

describe('a page whose clock is not the PC\'s (the phone)', () => {
  it('judges a frame\'s lateness and stamps an order on the PC\'s clock', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000_000);
    // This phone's clock runs 3 s behind the PC's.
    setDeskClockOffsetMs(3_000);
    expect(deskNow()).toBe(1_000_003_000);
    // The PC sent the book 40 ms ago, by its own clock.
    const sentSec = (deskNow() - 40) / 1000;
    noteSubscribed('ABCD', 'backend-1');
    noteBookFrame('ABCD', { seq: 9, at: sentSec, sent: sentSec });
    noteBookShown('ABCD', 9, 4.81, 4.82);
    noteBeat('ABCD', { seq: 9, now: deskNow() / 1000 });
    // On the phone's own clock that book would read 3 s early or late; on the PC's it is 40 ms old and live.
    expect(viewLockReason('ABCD')).toBeNull();
    expect(viewStampFor('ABCD', deskNow()).desk?.transit_ms).toBeLessThan(100);

    const fetchMock = answering({ ok: true, order_id: 7 });
    await placeIbkrOrder({ symbol: 'ABCD', side: 'BUY', qty: 1, order_type: 'MKT', outside_rth: false });
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body)) as { view: { action_wall_ms: number; book: { seq: number } }; client_timing: { action_wall_ms: number } };
    expect(body.view.action_wall_ms).toBe(1_000_003_000);
    expect(body.client_timing.action_wall_ms).toBe(1_000_003_000);
    expect(body.view.book.seq).toBe(9);
  });

  it('with no offset the PC\'s clock is the page\'s own, as on the desk', () => {
    vi.useFakeTimers();
    vi.setSystemTime(5_000);
    expect(deskNow()).toBe(5_000);
    setDeskClockOffsetMs(null);
    expect(deskNow()).toBe(5_000);
  });
});
