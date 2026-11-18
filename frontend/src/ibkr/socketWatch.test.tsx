/**
 * @vitest-environment jsdom
 *
 * A socket that went quiet is told from a market that went quiet, and the phone's tape refills what a drop cost
 * (operator report 2026-11-17: on the phone "the time and sale was not moving ... there was a missing piece").
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LINK_OPEN_MS, LINK_QUIET_MS, LINK_WAKE_GRACE_MS } from '../constantGroups/market_view';
import { clearBarsStoreForTests, getBarsEntry } from '../chart/barsStore';
import { viewLockReason } from '../market_view';
import { SocketWatch } from './socketWatch';
import { useIbkrDepth } from './useIbkrDepth';
import { useIbkrTape, type TapeOptions, type TapeState } from './useIbkrTape';

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (hidden ? 'hidden' : 'visible') });
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('SocketWatch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-17T19:35:00Z'));
    setHidden(false);
  });
  afterEach(() => {
    setHidden(false);
    vi.useRealTimers();
  });

  it('says a socket that spoke and then said nothing is quiet, once, with the moment it last spoke', () => {
    const quiet = vi.fn();
    const watch = new SocketWatch({ quiet });
    watch.opened();
    vi.advanceTimersByTime(1_000);
    watch.heard();
    const spokeAt = Date.now();
    vi.advanceTimersByTime(LINK_QUIET_MS - 100);
    expect(quiet).not.toHaveBeenCalled();
    vi.advanceTimersByTime(700);
    expect(quiet).toHaveBeenCalledTimes(1);
    expect(quiet).toHaveBeenCalledWith(spokeAt);
    vi.advanceTimersByTime(60_000);
    expect(quiet).toHaveBeenCalledTimes(1);          // once per socket: its owner replaces it
    watch.dispose();
  });

  it('gives a socket that has said nothing yet longer: the backend may be asking IBKR for the line', () => {
    const quiet = vi.fn();
    const watch = new SocketWatch({ quiet });
    watch.opened();
    vi.advanceTimersByTime(LINK_QUIET_MS + 2_000);
    expect(quiet).not.toHaveBeenCalled();
    vi.advanceTimersByTime(LINK_OPEN_MS);
    expect(quiet).toHaveBeenCalledTimes(1);
    watch.dispose();
  });

  it('a socket that keeps speaking is never quiet, however little it says', () => {
    const quiet = vi.fn();
    const watch = new SocketWatch({ quiet });
    watch.opened();
    for (let i = 0; i < 120; i += 1) {
      vi.advanceTimersByTime(1_000);                  // the tape's ping, once a second, for two minutes
      watch.heard();
    }
    expect(quiet).not.toHaveBeenCalled();
    watch.dispose();
  });

  it('never judges a hidden page, and a page coming back gets a moment to speak before it is judged', () => {
    const quiet = vi.fn();
    const woke = vi.fn();
    const watch = new SocketWatch({ quiet, woke });
    watch.opened();
    watch.heard();
    setHidden(true);
    vi.advanceTimersByTime(120_000);                  // the phone was locked for two minutes
    expect(quiet).not.toHaveBeenCalled();
    setHidden(false);
    expect(woke).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(LINK_WAKE_GRACE_MS - 600);
    expect(quiet).not.toHaveBeenCalled();             // its backlog may still be arriving
    vi.advanceTimersByTime(1_200);
    expect(quiet).toHaveBeenCalledTimes(1);           // a dead socket is replaced within two seconds of waking
    watch.dispose();
  });

  it('a closed socket is not watched, and the next one starts fresh', () => {
    const quiet = vi.fn();
    const watch = new SocketWatch({ quiet });
    watch.opened();
    watch.heard();
    watch.closed();
    vi.advanceTimersByTime(60_000);
    expect(quiet).not.toHaveBeenCalled();
    watch.opened();
    vi.advanceTimersByTime(LINK_OPEN_MS + 600);
    expect(quiet).toHaveBeenCalledTimes(1);
    watch.dispose();
  });
});

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  closed = false;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3;
    this.closed = true;
    this.onclose?.({});
  }

  send() {}

  say(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

const PHONE: TapeOptions = { watchLink: true, recent: 40 };

function print(seq: number, price: number, at = '2026-11-17T19:35:01.000Z'): Record<string, unknown> {
  return { type: 'print', symbol: 'GMM', time: at, price, size: 100, exchange: 'ARCA', seq, exchange_ts: 1794944101 };
}

describe('a tape that watches its link (the phone)', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: TapeState | null;
  let options: TapeOptions;

  function Harness() {
    latest = useIbkrTape('GMM', true, options);
    return null;
  }

  function mount(opts: TapeOptions = PHONE) {
    options = opts;
    act(() => {
      root.render(<Harness />);
    });
  }

  const sockets = () => FakeWebSocket.instances.filter((ws) => ws.url.includes('/ws/ibkr/tape/'));
  // One painted frame: the fake clock's frame grid is not at 16 ms once the system time is set.
  const frame = () => act(() => { vi.advanceTimersByTime(40); });

  beforeEach(() => {
    FakeWebSocket.instances = [];
    clearBarsStoreForTests();
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16) as unknown as number);
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-17T19:35:00Z'));
    setHidden(false);
  });

  afterEach(() => {
    act(() => { root.unmount(); });
    container.remove();
    setHidden(false);
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('asks the PC for the prints it holds, and shows them without feeding the candles', () => {
    mount();
    expect(sockets()[0].url).toMatch(/front=1&recent=40$/);
    act(() => {
      sockets()[0].say({ type: 'subscribed', symbol: 'GMM' });
      sockets()[0].say({ type: 'prints', symbol: 'GMM', recent: true, items: [print(101, 1.29), print(102, 1.3)] });
    });
    frame();
    expect(latest?.prints.map((p) => p.price)).toEqual([1.3, 1.29]);      // newest first, as live
    expect(getBarsEntry('GMM', '10Sec')?.bars ?? []).toEqual([]);          // held prints are for the rows only
    act(() => { sockets()[0].say(print(103, 1.31)); });
    frame();
    expect(latest?.prints.map((p) => p.price)).toEqual([1.31, 1.3, 1.29]);
    expect((getBarsEntry('GMM', '10Sec')?.bars ?? []).length).toBe(1);     // a live print still makes its candle
  });

  it('a socket that goes quiet is said, holds new buys, and is replaced at once with the gap asked for', () => {
    mount();
    act(() => {
      sockets()[0].say({ type: 'subscribed', symbol: 'GMM' });
      sockets()[0].say(print(101, 1.29));
    });
    frame();
    expect(latest?.quietSince).toBeNull();
    // The link under the socket died: no print, no ping, and the browser has not noticed.
    act(() => { vi.advanceTimersByTime(LINK_QUIET_MS + 600); });
    expect(latest?.quietSince).not.toBeNull();
    expect(latest?.connected).toBe(false);
    expect(viewLockReason('GMM')).toMatch(/^This screen's Time & Sales has had no word from your PC for /);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[0].closed).toBe(true);
    expect(sockets()[1].url).toMatch(/front=1&recent=40&after=101$/);      // the same front, and only what it lacks
    // The PC answers with what it held: the one print missed, and one the phone already has.
    act(() => {
      sockets()[1].say({ type: 'subscribed', symbol: 'GMM' });
      sockets()[1].say({ type: 'prints', symbol: 'GMM', recent: true, items: [print(101, 1.29), print(102, 1.3)] });
    });
    frame();
    expect(latest?.quietSince).toBeNull();
    expect(viewLockReason('GMM')).toBeNull();
    expect(latest?.prints.map((p) => p.price)).toEqual([1.3, 1.29]);       // no hole, and nothing twice
    expect(latest?.prints.map((p) => p.seq)).toEqual([102, 101]);
  });

  it('pings alone keep it live: a stock that does not trade is not a quiet socket', () => {
    mount();
    act(() => { sockets()[0].say({ type: 'subscribed', symbol: 'GMM' }); });
    for (let i = 0; i < 60; i += 1) {
      act(() => {
        vi.advanceTimersByTime(1_000);
        sockets()[0].say({ type: 'ping', symbol: 'GMM', silence: null, gate: null });
      });
    }
    expect(sockets()).toHaveLength(1);
    expect(latest?.quietSince).toBeNull();
  });

  it('a reconnect waiting on its backoff is made the moment the page comes back', () => {
    mount();
    act(() => { sockets()[0].say({ type: 'subscribed', symbol: 'GMM' }); });
    act(() => { setHidden(true); });
    act(() => { sockets()[0].close(); });            // the phone's browser dropped it while the page slept
    expect(sockets()).toHaveLength(1);               // the backoff has not fired
    act(() => { setHidden(false); });
    expect(sockets()).toHaveLength(2);               // asked for again now, not a second (or thirty) later
  });

  it('the desk tape is unchanged: no recent, no watch, no reconnect by itself', () => {
    mount({ traderTab: true });
    expect(sockets()[0].url).toMatch(/\?tab=1&front=1$/);
    act(() => { sockets()[0].say({ type: 'subscribed', symbol: 'GMM' }); });
    act(() => { vi.advanceTimersByTime(120_000); });
    expect(sockets()).toHaveLength(1);
    expect(latest && 'quietSince' in latest).toBe(false);
  });
});

describe('a Level 2 that watches its link (the phone)', () => {
  let container: HTMLDivElement;
  let root: Root;
  let quietSince: number | null | undefined;

  function Harness({ watchLink }: { watchLink: boolean }) {
    quietSince = useIbkrDepth('GMM', true, { watchLink }).quietSince;
    return null;
  }

  const sockets = () => FakeWebSocket.instances.filter((ws) => ws.url.includes('/ws/ibkr/depth/'));

  beforeEach(() => {
    FakeWebSocket.instances = [];
    quietSince = undefined;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-17T19:35:00Z'));
    setHidden(false);
  });

  afterEach(() => {
    act(() => { root.unmount(); });
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a socket that never answers is said and asked for again, where it used to read "Opening Level 2" for good', () => {
    act(() => { root.render(<Harness watchLink />); });
    expect(sockets()).toHaveLength(1);
    act(() => { vi.advanceTimersByTime(LINK_OPEN_MS + 600); });
    expect(quietSince).not.toBeNull();
    expect(viewLockReason('GMM')).toMatch(/^This screen's Level 2 has had no word from your PC for /);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toMatch(/front=1$/);
    act(() => { sockets()[1].say({ type: 'subscribed', symbol: 'GMM', instance: 'a' }); });
    expect(quietSince).toBeNull();
  });

  it('leaving the screen lifts its lock', () => {
    act(() => { root.render(<Harness watchLink />); });
    act(() => { vi.advanceTimersByTime(LINK_OPEN_MS + 600); });
    expect(viewLockReason('GMM')).not.toBeNull();
    act(() => { root.render(<div />); });
    expect(viewLockReason('GMM')).toBeNull();
  });

  it('the desk ladder is unchanged', () => {
    act(() => { root.render(<Harness watchLink={false} />); });
    act(() => { vi.advanceTimersByTime(120_000); });
    expect(sockets()).toHaveLength(1);
    expect(quietSince).toBeUndefined();
  });
});
