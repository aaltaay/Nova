/**
 * The phone link test (ADR 070): one light page that measures the link between this device and
 * Nova on the PC, before any phone layout is built on it. It reads only -- it holds no API key and
 * sends no order.
 *
 * For one symbol it opens the desk's own Level 2 and Time & Sales sockets and, once a second, asks
 * the order gate's read route. From those it shows the round trip, this device's clock against the
 * PC's, how old each Level 2 and tape frame is on arrival, and how much traffic the symbol makes.
 *
 * It is built to be left running: a socket that drops or goes silent dials again, every drop is
 * timed, and the whole run keeps its own count beside the last 30 seconds.
 */
import {
  CLOCK_SAMPLES_KEEP,
  FAILED_ROUND_TRIP_MS,
  LINK_LIMIT_MS,
  Outages,
  PING_TIMEOUT_MS,
  RECONNECT_WAIT_MS,
  Rolling,
  SILENCE_LIMIT_MS,
  Tally,
  apiBaseFor,
  bestClock,
  clockSample,
  durationText,
  frameAgeMs,
  linkVerdict,
  wsBaseFor,
  type ClockSample,
  type Spread,
} from './linkStats';

const API_BASE = apiBaseFor(window.location);
const WS_BASE = wsBaseFor(API_BASE);
const PING_EVERY_MS = 1_000;
const DRAW_EVERY_MS = 500;

const STYLE = `
  :root { color-scheme: dark; }
  body { margin: 0; background: #0f1115; color: #e6e8eb; font: 15px/1.4 system-ui, sans-serif; }
  main { max-width: 520px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  p { margin: 0 0 12px; color: #9aa3ad; }
  form { display: flex; gap: 8px; margin-bottom: 12px; }
  input { flex: 1; min-width: 0; padding: 10px; font-size: 16px; text-transform: uppercase;
          background: #171a21; color: inherit; border: 1px solid #2a2f3a; border-radius: 6px; }
  button { padding: 10px 14px; font-size: 15px; background: #232836; color: inherit;
           border: 1px solid #2a2f3a; border-radius: 6px; }
  #verdict { padding: 12px; border-radius: 6px; font-weight: 600; margin-bottom: 12px; background: #171a21; }
  #verdict.pass { background: #12301f; color: #6ee7a0; }
  #verdict.fail { background: #3a1518; color: #ff8a8a; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th, td { text-align: right; padding: 6px 4px; border-bottom: 1px solid #1d212b; }
  th:first-child, td:first-child { text-align: left; }
  th { color: #9aa3ad; font-weight: 500; font-size: 12px; }
  td.over { color: #ff8a8a; }
  h2 { font-size: 13px; font-weight: 500; color: #9aa3ad; margin: 16px 0 4px; }
  #whole, #notes { color: #c5cbd3; font-size: 13px; white-space: pre-line; font-variant-numeric: tabular-nums; }
  #notes { margin-top: 12px; color: #9aa3ad; }
`;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', id = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (id) node.id = id;
  return node;
}

type FeedName = 'Level 2' | 'Time & Sales';

interface Feed {
  name: FeedName;
  path: string;
  /** Level 2 beats four times a second, so silence means a dead socket; the tape is quiet whenever nobody trades. */
  beats: boolean;
  recent: Rolling;
  whole: Tally;
  outages: Outages;
  ws: WebSocket | null;
  lastFrameAt: number | null;
  retry: number | null;
}

interface Run {
  symbol: string;
  startedWall: number;
  roundTrip: Rolling;
  roundTripWhole: Tally;
  feeds: Feed[];
  clock: ClockSample[];
  timers: number[];
  notes: Map<string, string>;
  gate: string;
  failedPings: number;
  /** Time the page was hidden (screen off, another app): the browser stops it, so nothing is measured. */
  hiddenMs: number;
  hiddenAt: number | null;
}

let run: Run | null = null;

function newFeed(name: FeedName, path: string, beats: boolean): Feed {
  return { name, path, beats, recent: new Rolling(), whole: new Tally(), outages: new Outages(), ws: null, lastFrameAt: null, retry: null };
}

function offsetMs(r: Run): number | null {
  return bestClock(r.clock)?.offsetMs ?? null;
}

async function ping(r: Run): Promise<void> {
  if (r.hiddenAt != null) return;
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
    if (run !== r) return;
    r.roundTrip.add(Date.now(), rtt);
    r.roundTripWhole.add(rtt);
    if (typeof body.checked_at === 'number') {
      r.clock.push(clockSample(asked, asked + rtt, body.checked_at));
      if (r.clock.length > CLOCK_SAMPLES_KEEP) r.clock.shift();
    }
    r.gate = body.locked ? `locked: ${body.text ?? ''}` : 'open';
  } catch (err) {
    if (run !== r || r.hiddenAt != null) return;
    // A failed round trip is a slow one, not a missing one: it counts against the verdict.
    r.roundTrip.add(Date.now(), FAILED_ROUND_TRIP_MS);
    r.roundTripWhole.add(FAILED_ROUND_TRIP_MS);
    r.failedPings += 1;
    r.notes.set('round trip', `Round trips failed: ${r.failedPings} (each counted as ${FAILED_ROUND_TRIP_MS} ms). Last: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    window.clearTimeout(timeout);
  }
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
    if (type === 'error' || type === 'lent') {
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
    const counted = type === 'book' || type === 'beat' || type === 'print' || type === 'prints';
    if (!counted) return;
    const offset = offsetMs(r);
    const age = offset == null ? null : frameAgeMs(now, offset, sent);
    feed.recent.add(now, age, raw.length);
    feed.whole.add(age);
  };
  ws.onclose = (ev) => {
    if (run !== r || feed.ws !== ws) return;
    redial(r, feed, `socket closed (${ev.code})`);
  };
}

/** Once a second: a beating feed with nothing for too long is dead even when its socket still looks open. */
function watch(r: Run): void {
  if (r.hiddenAt != null) return;
  const now = Date.now();
  const dead = r.feeds.find((f) => f.beats && f.ws != null && f.lastFrameAt != null && now - f.lastFrameAt > SILENCE_LIMIT_MS);
  if (!dead) return;
  // The drop began at the last frame heard, not when the silence was noticed. Every feed rides the
  // same link, so the quiet tape, which cannot show it is dead, dials again with it.
  const since = dead.lastFrameAt ?? now;
  for (const feed of r.feeds) {
    if (feed.ws != null) redial(r, feed, feed === dead ? `silent for ${(SILENCE_LIMIT_MS / 1000).toFixed(0)} s` : 'the link dropped', since);
  }
}

function onVisibility(): void {
  const r = run;
  if (!r) return;
  const now = Date.now();
  if (document.hidden) {
    r.hiddenAt = now;
    return;
  }
  if (r.hiddenAt != null) r.hiddenMs += now - r.hiddenAt;
  r.hiddenAt = null;
  // The browser froze the page: give each feed a fresh allowance before silence counts as a drop.
  for (const feed of r.feeds) if (feed.lastFrameAt != null) feed.lastFrameAt = now;
  void keepAwake(r);
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

function stop(): void {
  if (!run) return;
  const r = run;
  run = null;
  r.timers.forEach((t) => window.clearInterval(t));
  for (const feed of r.feeds) {
    if (feed.retry != null) window.clearTimeout(feed.retry);
    feed.ws?.close();
  }
}

function ms(value: number | undefined, limit = LINK_LIMIT_MS): { text: string; over: boolean } {
  if (value == null) return { text: '--', over: false };
  return { text: `${Math.round(value)}`, over: value > limit };
}

function fillRow(row: HTMLTableRowElement, spread: Spread | null, rate: string): void {
  const cells = [ms(spread?.p50), ms(spread?.p95), ms(spread?.max)];
  cells.forEach((cell, i) => {
    const td = row.cells[i + 1];
    td.textContent = cell.text;
    td.className = cell.over ? 'over' : '';
  });
  row.cells[4].textContent = rate;
}

function rateText(r: { perSec: number; bytesPerSec: number }): string {
  return `${r.perSec.toFixed(1)}/s · ${(r.bytesPerSec / 1024).toFixed(1)} kB/s`;
}

function network(): string {
  const conn = (navigator as Navigator & { connection?: { effectiveType?: string; type?: string } }).connection;
  return conn ? [conn.type, conn.effectiveType].filter(Boolean).join(' / ') || 'unknown' : 'not reported by this browser';
}

function clockText(clock: ClockSample | null): string {
  if (!clock) return 'Clock: not measured yet, so ages wait.';
  const by = Math.round(Math.abs(clock.offsetMs));
  return `Clock: the PC is ${by} ms ${clock.offsetMs >= 0 ? 'ahead of' : 'behind'} this device (good to ${Math.round(clock.rttMs / 2)} ms).`;
}

/** The whole run, where the table above only knows the last 30 seconds. */
function wholeRun(r: Run, now: number): string[] {
  const hidden = r.hiddenMs + (r.hiddenAt == null ? 0 : now - r.hiddenAt);
  return [
    `Ran ${durationText(now - r.startedWall - hidden)}${hidden ? ` (screen off or page hidden ${durationText(hidden)}, not measured)` : ''}`,
    `Round trips: ${r.roundTripWhole.text()}${r.failedPings ? `, failed ${r.failedPings}` : ''}`,
    ...r.feeds.map((feed) => `${feed.name}: ${feed.whole.text()} · ${feed.outages.text(now)}`),
  ];
}

function summary(r: Run, now: number): string {
  const line = (label: string, s: Spread | null) =>
    `${label}: ${s ? `p50 ${Math.round(s.p50)} / p95 ${Math.round(s.p95)} / max ${Math.round(s.max)} ms (n ${s.n})` : 'no data'}`;
  const [book, tape] = r.feeds;
  return [
    `Nova link test · ${r.symbol} · ${new Date(now).toISOString()}`,
    `Page ${window.location.origin} · network ${network()}`,
    'Last 30 s:',
    line('Round trip', r.roundTrip.spread(now)),
    line('Level 2 age', book.recent.spread(now)) + ` · ${rateText(book.recent.rate(now))}`,
    line('Tape age', tape.recent.spread(now)) + ` · ${rateText(tape.recent.rate(now))}`,
    'Whole run:',
    ...wholeRun(r, now),
    clockText(bestClock(r.clock)),
    `Order gate: ${r.gate}`,
    `Verdict (${LINK_LIMIT_MS} ms, last 30 s): ${linkVerdict(book.recent.spread(now), r.roundTrip.spread(now))}`,
    ...r.notes.values(),
  ].join('\n');
}

function build(): void {
  document.head.append(el('style', STYLE));
  const main = el('main');
  main.append(
    el('h1', 'Nova link test'),
    el('p', 'Measures this device against Nova on the PC. Reads only: no key, no orders.'),
  );
  const form = el('form');
  const input = el('input');
  input.placeholder = 'Symbol open on the desk';
  input.autocapitalize = 'characters';
  input.maxLength = 16;
  const startButton = el('button', 'Start');
  startButton.type = 'submit';
  const copyButton = el('button', 'Copy');
  copyButton.type = 'button';
  form.append(input, startButton, copyButton);

  const verdict = el('div', 'Enter a symbol and press Start.', 'verdict');
  const table = el('table');
  const head = table.insertRow();
  ['Last 30 s', 'p50 ms', 'p95 ms', 'max ms', 'traffic'].forEach((h) => head.append(el('th', h)));
  const rows = ['Round trip', 'Level 2 age', 'Tape age'].map((label) => {
    const row = table.insertRow();
    row.append(el('td', label), el('td', '--'), el('td', '--'), el('td', '--'), el('td', ''));
    return row;
  });
  const whole = el('div', '', 'whole');
  const notes = el('div', '', 'notes');
  main.append(form, verdict, table, el('h2', 'Whole run'), whole, notes);
  document.body.append(main);

  const draw = (): void => {
    const r = run;
    if (!r) return;
    const now = Date.now();
    const [bookFeed, tapeFeed] = r.feeds;
    const roundTrip = r.roundTrip.spread(now);
    const book = bookFeed.recent.spread(now);
    fillRow(rows[0], roundTrip, '1.0/s');
    fillRow(rows[1], book, rateText(bookFeed.recent.rate(now)));
    fillRow(rows[2], tapeFeed.recent.spread(now), rateText(tapeFeed.recent.rate(now)));
    const v = linkVerdict(book, roundTrip);
    verdict.className = v === 'waiting' ? '' : v;
    verdict.textContent =
      v === 'pass' ? `Under ${LINK_LIMIT_MS} ms: 95 in 100 of the data and the round trips.`
      : v === 'fail' ? `Over ${LINK_LIMIT_MS} ms: not usable for orders on this connection.`
      : `Measuring ${r.symbol}...`;
    whole.textContent = wholeRun(r, now).join('\n');
    notes.textContent = [
      clockText(bestClock(r.clock)),
      `Order gate for ${r.symbol}: ${r.gate}`,
      `Network: ${network()}`,
      ...r.notes.values(),
    ].join('\n');
  };

  document.addEventListener('visibilitychange', onVisibility);

  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    if (run) {
      stop();
      startButton.textContent = 'Start';
      return;
    }
    const symbol = input.value.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,16}$/.test(symbol)) {
      verdict.textContent = 'Enter a stock symbol.';
      return;
    }
    const r: Run = {
      symbol, startedWall: Date.now(), roundTrip: new Rolling(), roundTripWhole: new Tally(),
      feeds: [newFeed('Level 2', '/ws/ibkr/depth', true), newFeed('Time & Sales', '/ws/ibkr/tape', false)],
      clock: [], timers: [], notes: new Map(), gate: 'not read yet', failedPings: 0, hiddenMs: 0, hiddenAt: null,
    };
    run = r;
    startButton.textContent = 'Stop';
    copyButton.textContent = 'Copy';
    void ping(r);
    void keepAwake(r);
    r.timers.push(
      window.setInterval(() => void ping(r), PING_EVERY_MS),
      window.setInterval(() => watch(r), PING_EVERY_MS),
      window.setInterval(draw, DRAW_EVERY_MS),
    );
    r.feeds.forEach((feed) => openSocket(r, feed));
    draw();
  });

  copyButton.addEventListener('click', () => {
    if (!run) return;
    const text = summary(run, Date.now());
    navigator.clipboard?.writeText(text).then(
      () => { copyButton.textContent = 'Copied'; },
      () => { notes.textContent = text; },
    );
  });
}

build();
