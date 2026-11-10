/**
 * The phone link test (ADR 070): one light page that measures the link between this device and
 * Nova on the PC, before any phone layout is built on it. It reads only -- it holds no API key and
 * sends no order.
 *
 * For one symbol it opens the desk's own Level 2 and Time & Sales sockets and, once a second, asks
 * the order gate's read route. From those it shows the round trip, this device's clock against the
 * PC's, how old each Level 2 and tape frame is on arrival, and how much traffic the symbol makes.
 */
import {
  CLOCK_SAMPLES_KEEP,
  FAILED_ROUND_TRIP_MS,
  LINK_LIMIT_MS,
  PING_TIMEOUT_MS,
  Rolling,
  apiBaseFor,
  bestClock,
  clockSample,
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
  #notes { margin-top: 12px; color: #9aa3ad; font-size: 13px; white-space: pre-line; }
`;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', id = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (id) node.id = id;
  return node;
}

interface Run {
  symbol: string;
  startedWall: number;
  roundTrip: Rolling;
  book: Rolling;
  tape: Rolling;
  clock: ClockSample[];
  sockets: WebSocket[];
  timers: number[];
  notes: Map<string, string>;
  gate: string;
  failedPings: number;
}

let run: Run | null = null;

function offsetMs(r: Run): number | null {
  return bestClock(r.clock)?.offsetMs ?? null;
}

async function ping(r: Run): Promise<void> {
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
    if (typeof body.checked_at === 'number') {
      r.clock.push(clockSample(asked, asked + rtt, body.checked_at));
      if (r.clock.length > CLOCK_SAMPLES_KEEP) r.clock.shift();
    }
    r.gate = body.locked ? `locked: ${body.text ?? ''}` : 'open';
  } catch (err) {
    if (run !== r) return;
    // A failed round trip is a slow one, not a missing one: it counts against the verdict.
    r.roundTrip.add(Date.now(), FAILED_ROUND_TRIP_MS);
    r.failedPings += 1;
    r.notes.set('round trip', `Round trips failed: ${r.failedPings} (each counted as ${FAILED_ROUND_TRIP_MS} ms). Last: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    window.clearTimeout(timeout);
  }
}

function openSocket(r: Run, name: 'Level 2' | 'Time & Sales', path: string, into: Rolling): void {
  const ws = new WebSocket(`${WS_BASE}${path}/${encodeURIComponent(r.symbol)}`);
  r.sockets.push(ws);
  ws.onmessage = (ev) => {
    if (run !== r) return;
    const now = Date.now();
    const raw = typeof ev.data === 'string' ? ev.data : '';
    let frame: Record<string, unknown>;
    try {
      frame = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      r.notes.set(name, `${name}: a frame that is not JSON`);
      return;
    }
    const type = frame.type;
    if (type === 'error' || type === 'lent') {
      r.notes.set(name, `${name}: ${String(frame.message ?? frame.text ?? type)}`);
      return;
    }
    if (type === 'subscribed') {
      r.notes.delete(name);
      return;
    }
    // A book or a batch of prints says when it was sent; a beat says the PC's clock now; one print, when it arrived there.
    const sent = type === 'beat' ? frame.now : type === 'print' ? frame.ts : frame.sent;
    const offset = offsetMs(r);
    const counted = type === 'book' || type === 'beat' || type === 'print' || type === 'prints';
    if (!counted) return;
    into.add(now, offset == null ? null : frameAgeMs(now, offset, sent), raw.length);
  };
  ws.onclose = (ev) => {
    if (run !== r) return;
    if (!r.notes.has(name)) r.notes.set(name, `${name}: socket closed (${ev.code})`);
  };
}

function stop(): void {
  if (!run) return;
  run.timers.forEach((t) => window.clearInterval(t));
  run.sockets.forEach((ws) => ws.close());
  run = null;
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

function summary(r: Run, now: number): string {
  const line = (label: string, s: Spread | null) =>
    `${label}: ${s ? `p50 ${Math.round(s.p50)} / p95 ${Math.round(s.p95)} / max ${Math.round(s.max)} ms (n ${s.n})` : 'no data'}`;
  const clock = bestClock(r.clock);
  return [
    `Nova link test · ${r.symbol} · ${new Date(now).toISOString()} · ${Math.round((now - r.startedWall) / 1000)} s`,
    `Page ${window.location.origin} · network ${network()}`,
    line('Round trip', r.roundTrip.spread(now)),
    line('Level 2 age', r.book.spread(now)) + ` · ${rateText(r.book.rate(now))}`,
    line('Tape age', r.tape.spread(now)) + ` · ${rateText(r.tape.rate(now))}`,
    clock ? `Clock: PC minus this device ${Math.round(clock.offsetMs)} ms (good to ${Math.round(clock.rttMs / 2)} ms)` : 'Clock: not measured',
    `Order gate: ${r.gate}`,
    `Verdict (${LINK_LIMIT_MS} ms): ${linkVerdict(r.book.spread(now), r.roundTrip.spread(now))}`,
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
  ['', 'p50 ms', 'p95 ms', 'max ms', 'traffic'].forEach((h) => head.append(el('th', h)));
  const rows = ['Round trip', 'Level 2 age', 'Tape age'].map((label) => {
    const row = table.insertRow();
    row.append(el('td', label), el('td', '--'), el('td', '--'), el('td', '--'), el('td', ''));
    return row;
  });
  const notes = el('div', '', 'notes');
  main.append(form, verdict, table, notes);
  document.body.append(main);

  const draw = (): void => {
    const r = run;
    if (!r) return;
    const now = Date.now();
    const roundTrip = r.roundTrip.spread(now);
    const book = r.book.spread(now);
    fillRow(rows[0], roundTrip, '1.0/s');
    fillRow(rows[1], book, rateText(r.book.rate(now)));
    fillRow(rows[2], r.tape.spread(now), rateText(r.tape.rate(now)));
    const v = linkVerdict(book, roundTrip);
    verdict.className = v === 'waiting' ? '' : v;
    verdict.textContent =
      v === 'pass' ? `Under ${LINK_LIMIT_MS} ms: 95 in 100 of the data and the round trips.`
      : v === 'fail' ? `Over ${LINK_LIMIT_MS} ms: not usable for orders on this connection.`
      : `Measuring ${r.symbol}...`;
    const clock = bestClock(r.clock);
    notes.textContent = [
      clock ? `Clock: the PC is ${Math.round(clock.offsetMs)} ms ${clock.offsetMs >= 0 ? 'ahead of' : 'behind'} this device (good to ${Math.round(clock.rttMs / 2)} ms).` : 'Clock: not measured yet, so ages wait.',
      `Order gate for ${r.symbol}: ${r.gate}`,
      `Network: ${network()}`,
      ...r.notes.values(),
    ].join('\n');
  };

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
      symbol, startedWall: Date.now(), roundTrip: new Rolling(), book: new Rolling(), tape: new Rolling(),
      clock: [], sockets: [], timers: [], notes: new Map(), gate: 'not read yet', failedPings: 0,
    };
    run = r;
    startButton.textContent = 'Stop';
    void ping(r);
    r.timers.push(window.setInterval(() => void ping(r), PING_EVERY_MS), window.setInterval(draw, DRAW_EVERY_MS));
    openSocket(r, 'Level 2', '/ws/ibkr/depth', r.book);
    openSocket(r, 'Time & Sales', '/ws/ibkr/tape', r.tape);
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
