/**
 * One run of the phone link test (ADR 070): the measuring, with no screen. For one symbol it asks
 * the order gate's read route once a second and holds the desk's own Level 2 and Time & Sales
 * sockets, and keeps what they show. It reads only -- no API key, no order (orders are `linkOrders.ts`).
 *
 * It is built to be left running: a socket that closes or goes silent dials again, every drop is
 * timed from the last frame heard to the first frame back, and time the page was hidden (the
 * browser freezes a hidden page) is taken out of every measure.
 */
import {
  CLOCK_SAMPLES_KEEP,
  FAILED_ROUND_TRIP_MS,
  Outages,
  PING_TIMEOUT_MS,
  RECONNECT_WAIT_MS,
  Rolling,
  SILENCE_LIMIT_MS,
  Tally,
  apiBaseFor,
  bestClock,
  clockSample,
  frameAgeMs,
  wsBaseFor,
  type ClockSample,
} from './linkStats';

import type { OrderContext } from './linkOrders';

export const API_BASE = apiBaseFor(window.location);
const WS_BASE = wsBaseFor(API_BASE);
const PING_EVERY_MS = 1_000;

export type FeedName = 'Level 2' | 'Time & Sales';

export interface Feed {
  name: FeedName;
  path: string;
  recent: Rolling;
  whole: Tally;
  outages: Outages;
  ws: WebSocket | null;
  lastFrameAt: number | null;
  retry: number | null;
}

export interface Run {
  symbol: string;
  startedWall: number;
  roundTrip: Rolling;
  roundTripWhole: Tally;
  /** Level 2 first, then Time & Sales. */
  feeds: Feed[];
  clock: ClockSample[];
  timers: number[];
  notes: Map<string, string>;
  gate: string;
  failedPings: number;
  /** Time the page was hidden (screen off, another app): the browser stops it, so nothing is measured. */
  hiddenMs: number;
  hiddenAt: number | null;
  /** Counts every hide and show, so a round trip that was in flight across one is thrown away. */
  spans: number;
  /** The backend process the Level 2 socket subscribed to, and the last book it sent. */
  instance: string | null;
  book: OrderContext['book'];
}

let run: Run | null = null;

/** The run in progress, or null. */
export function currentRun(): Run | null {
  return run;
}

function newFeed(name: FeedName, path: string): Feed {
  return { name, path, recent: new Rolling(), whole: new Tally(), outages: new Outages(), ws: null, lastFrameAt: null, retry: null };
}

async function ping(r: Run): Promise<void> {
  if (r.hiddenAt != null) return;
  const span = r.spans;
  // Hidden since it was asked, or hidden and shown again: the browser may have held it, so it measures nothing.
  const stale = (): boolean => run !== r || r.spans !== span;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), PING_TIMEOUT_MS);
  const asked = Date.now();
  const askedMono = performance.now();
  try {
    const res = await fetch(`${API_BASE}/api/market-view/gate?symbol=${encodeURIComponent(r.symbol)}`, {
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as { checked_at?: number; locked?: boolean; text?: string | null };
    const rtt = performance.now() - askedMono;
    if (stale()) return;
    r.roundTrip.add(Date.now(), rtt);
    r.roundTripWhole.add(rtt);
    if (typeof body.checked_at === 'number') {
      r.clock.push(clockSample(asked, asked + rtt, body.checked_at));
      if (r.clock.length > CLOCK_SAMPLES_KEEP) r.clock.shift();
    }
    r.gate = body.locked ? `locked: ${body.text ?? ''}` : 'open';
  } catch (err) {
    if (stale()) return;
    // A failed round trip is a slow one, not a missing one: it counts against the verdict.
    r.roundTrip.add(Date.now(), FAILED_ROUND_TRIP_MS);
    r.roundTripWhole.add(FAILED_ROUND_TRIP_MS);
    r.failedPings += 1;
    r.notes.set('round trip', `Round trips failed: ${r.failedPings} (each counted as ${FAILED_ROUND_TRIP_MS} ms). Last: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    window.clearTimeout(timeout);
  }
}

function topPrice(levels: unknown): number | null {
  const first = Array.isArray(levels) ? (levels[0] as { price?: unknown } | undefined) : undefined;
  return typeof first?.price === 'number' && Number.isFinite(first.price) ? first.price : null;
}

/** Keep which backend the Level 2 socket subscribed to and the last book it sent: an order's view (ADR 045). */
function noteView(r: Run, frame: Record<string, unknown>): void {
  if (frame.type === 'subscribed') {
    r.instance = typeof frame.instance === 'string' ? frame.instance : null;
    return;
  }
  if (frame.type !== 'book' || typeof frame.seq !== 'number') return;
  const data = (frame.data ?? {}) as { bids?: unknown; asks?: unknown };
  r.book = { seq: frame.seq, at: typeof frame.at === 'number' ? frame.at : null, bid: topPrice(data.bids), ask: topPrice(data.asks) };
}

/** What an order tapped now would carry, or null when no test runs. */
export function orderContext(): OrderContext | null {
  const r = run;
  if (!r) return null;
  return { symbol: r.symbol, offsetMs: bestClock(r.clock)?.offsetMs ?? null, instance: r.instance, book: r.book };
}

/** The feed went quiet: time the drop, hang up what is left of the socket, and dial again shortly. */
function redial(r: Run, feed: Feed, why: string, since: number = Date.now()): void {
  if (run !== r) return;
  feed.outages.down(since);
  r.notes.set(feed.name, `${feed.name}: ${why}; dialling again`);
  const old = feed.ws;
  feed.ws = null;
  if (old) {
    old.onclose = null;
    old.onmessage = null;
    old.close();
  }
  if (feed.retry != null) return;
  feed.retry = window.setTimeout(() => {
    feed.retry = null;
    if (run === r) openSocket(r, feed);
  }, RECONNECT_WAIT_MS);
}

function openSocket(r: Run, feed: Feed): void {
  const ws = new WebSocket(`${WS_BASE}${feed.path}/${encodeURIComponent(r.symbol)}`);
  feed.ws = ws;
  // A dial that never connects must not sit forever either.
  feed.lastFrameAt = Date.now();
  ws.onmessage = (ev) => {
    if (run !== r || feed.ws !== ws) return;
    const now = Date.now();
    feed.lastFrameAt = now;
    const raw = typeof ev.data === 'string' ? ev.data : '';
    let frame: Record<string, unknown>;
    try {
      frame = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      r.notes.set(feed.name, `${feed.name}: a frame that is not JSON`);
      return;
    }
    const type = frame.type;
    // What an order would be priced from is kept even while hidden: it is what this device holds, measured or not.
    if (feed.name === 'Level 2') noteView(r, frame);
    // A hidden page measures nothing: no sample, and an open drop ends on the first frame after it shows again.
    if (r.hiddenAt != null) return;
    if (type === 'error' || type === 'lane') {
      r.notes.set(feed.name, `${feed.name}: ${String(frame.message ?? frame.text ?? type)}`);
      return;
    }
    if (feed.outages.isDown()) {
      feed.outages.up(now);
      r.notes.delete(feed.name);
    }
    if (type === 'subscribed') {
      r.notes.delete(feed.name);
      return;
    }
    // A book or a batch of prints says when it was sent; a beat says the PC's clock now; one print, when it arrived there.
    const sent = type === 'beat' ? frame.now : type === 'print' ? frame.ts : frame.sent;
    // The tape's once-a-second ping proves the socket is alive and carries no time to age.
    const counted = type === 'book' || type === 'beat' || type === 'print' || type === 'prints';
    if (!counted) return;
    const offset = bestClock(r.clock)?.offsetMs ?? null;
    const age = offset == null ? null : frameAgeMs(now, offset, sent);
    feed.recent.add(now, age, raw.length);
    feed.whole.add(age);
  };
  ws.onclose = (ev) => {
    if (run !== r || feed.ws !== ws) return;
    redial(r, feed, `socket closed (${ev.code})`);
  };
}

/**
 * Once a second: both sockets carry a heartbeat (Level 2 a beat every 250 ms, the tape a ping every
 * second), so one with nothing for too long is dead even when it still looks open. Each is judged
 * on its own, and its drop began at the last frame heard, not when the silence was noticed.
 */
function watch(r: Run): void {
  if (r.hiddenAt != null) return;
  const now = Date.now();
  for (const feed of r.feeds) {
    if (feed.ws == null || feed.lastFrameAt == null || now - feed.lastFrameAt <= SILENCE_LIMIT_MS) continue;
    redial(r, feed, `silent for ${(SILENCE_LIMIT_MS / 1000).toFixed(0)} s`, feed.lastFrameAt);
  }
}

interface WakeLockNavigator {
  wakeLock?: { request(type: 'screen'): Promise<unknown> };
}

/** Ask the browser to keep the screen on, so a long run is not frozen by the lock screen. */
async function keepAwake(r: Run): Promise<void> {
  const lock = (navigator as Navigator & WakeLockNavigator).wakeLock;
  if (!lock) {
    r.notes.set('awake', 'This browser cannot keep the screen on: keep it awake by hand for a long run.');
    return;
  }
  try {
    await lock.request('screen');
    r.notes.delete('awake');
  } catch {
    r.notes.set('awake', 'The screen may turn off: the browser refused to keep it on.');
  }
}

/** The page was hidden or shown: stop measuring while hidden, and take that time out of every open drop. */
export function onVisibility(): void {
  const r = run;
  if (!r) return;
  const now = Date.now();
  r.spans += 1;
  if (document.hidden) {
    if (r.hiddenAt == null) r.hiddenAt = now;
    return;
  }
  if (r.hiddenAt != null) {
    r.hiddenMs += now - r.hiddenAt;
    for (const feed of r.feeds) feed.outages.skip(r.hiddenAt, now);
  }
  r.hiddenAt = null;
  // The browser froze the page: give each feed a fresh allowance before silence counts as a drop.
  for (const feed of r.feeds) if (feed.lastFrameAt != null) feed.lastFrameAt = now;
  void keepAwake(r);
}

/** Start measuring *symbol*; `draw` is called on the page's own beat. */
export function startRun(symbol: string, draw: () => void, drawEveryMs: number): Run {
  const r: Run = {
    symbol, startedWall: Date.now(), roundTrip: new Rolling(), roundTripWhole: new Tally(),
    feeds: [newFeed('Level 2', '/ws/ibkr/depth'), newFeed('Time & Sales', '/ws/ibkr/tape')],
    clock: [], timers: [], notes: new Map(), gate: 'not read yet', failedPings: 0, hiddenMs: 0, hiddenAt: null, spans: 0,
    instance: null, book: null,
  };
  run = r;
  void ping(r);
  void keepAwake(r);
  r.timers.push(
    window.setInterval(() => void ping(r), PING_EVERY_MS),
    window.setInterval(() => watch(r), PING_EVERY_MS),
    window.setInterval(draw, drawEveryMs),
  );
  r.feeds.forEach((feed) => openSocket(r, feed));
  return r;
}

export function stopRun(): void {
  if (!run) return;
  const r = run;
  run = null;
  r.timers.forEach((t) => window.clearInterval(t));
  for (const feed of r.feeds) {
    if (feed.retry != null) window.clearTimeout(feed.retry);
    feed.ws?.close();
  }
}
