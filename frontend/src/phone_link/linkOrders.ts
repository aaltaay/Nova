/**
 * The phone's Paper orders (ADR 070, amendment 2026-11-10): the calls to `/api/phone`, with no screen.
 *
 * The phone PIN buys a session token, kept in memory only -- a reload locks the phone again. Every
 * order carries when it was tapped on the PC's clock (this device's clock plus the offset the link
 * test measures) and the Level 2 version this device last received, so the order door judges a
 * phone order by the same stale-view rules as the desk's (ADR 045). Paper only: the backend refuses
 * anything else, whatever this file sends.
 */

const SESSION_HEADER = 'X-Nova-Phone-Session';
const TIMEOUT_MS = 8_000;

/** What the link test knows at the moment of a tap. */
export interface OrderContext {
  symbol: string;
  /** The PC's clock minus this device's, ms; null before the first round trip. */
  offsetMs: number | null;
  /** The backend process the Level 2 socket subscribed to. */
  instance: string | null;
  /** The last Level 2 book this device received. */
  book: { seq: number; at: number | null; bid: number | null; ask: number | null } | null;
}

export interface PhoneStatus {
  pin_set: boolean;
  unlocked: boolean;
  expires_at: number | null;
  venue: string;
  paper: boolean;
  armed: boolean;
}

/** One answer from Nova: whether it did what was asked, how long the tap took to be answered, and its words. */
export interface Answer {
  ok: boolean;
  ms: number;
  text: string;
  status?: PhoneStatus;
}

export interface OrderStamp {
  client_timing: { action_wall_ms: number; action_performance_ms: number; request_wall_ms: number; request_performance_ms: number };
  view: {
    schema_version: 1;
    symbol: string;
    action_wall_ms: number;
    instance: string | null;
    book: { seq: number; at: number | null; bid: number | null; ask: number | null } | null;
    quote: null;
    desk: null;
  };
}

/**
 * The timing and the view an order carries, on the PC's clock. Null before the clock is measured: an
 * order stamped on this device's own clock would be judged against the wrong time.
 */
export function orderStamp(ctx: OrderContext, wallMs: number, perfMs: number): OrderStamp | null {
  if (ctx.offsetMs == null) return null;
  const onPcClock = wallMs + ctx.offsetMs;
  return {
    client_timing: {
      action_wall_ms: onPcClock,
      action_performance_ms: perfMs,
      request_wall_ms: onPcClock,
      request_performance_ms: perfMs,
    },
    view: {
      schema_version: 1,
      symbol: ctx.symbol,
      action_wall_ms: onPcClock,
      instance: ctx.instance,
      book: ctx.book,
      quote: null,
      desk: null,
    },
  };
}

/** Nova's own words for a refusal, from whichever layer answered. */
export function refusalText(status: number, body: unknown): string {
  const b = (body ?? {}) as { detail?: unknown; error?: unknown };
  if (b.detail && typeof b.detail === 'object') {
    const d = b.detail as { error?: unknown; reason?: unknown };
    if (typeof d.error === 'string') return d.error;
    if (Array.isArray(b.detail)) return 'Nova did not accept that order as written.';
  }
  if (typeof b.detail === 'string') return b.detail;
  if (typeof b.error === 'string' && b.error) return b.error;
  return `Nova answered ${status}.`;
}

/** The side and size that close a position row from `/api/ibkr/positions`, or null when there is none. */
export function closingOrder(row: { qty?: unknown; position_side?: unknown } | undefined): { side: 'BUY' | 'SELL'; qty: number } | null {
  const qty = typeof row?.qty === 'number' ? row.qty : Number.NaN;
  if (!Number.isFinite(qty) || qty === 0) return null;
  const short = row?.position_side === 'short' || qty < 0;
  return { side: short ? 'BUY' : 'SELL', qty: Math.abs(qty) };
}

export class PhoneDoor {
  private token: string | null = null;
  private readonly apiBase: string;

  constructor(apiBase: string) {
    this.apiBase = apiBase;
  }

  private async call(method: string, path: string, body?: unknown): Promise<{ status: number; body: unknown; ms: number }> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
    const started = performance.now();
    const headers: Record<string, string> = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (this.token) headers[SESSION_HEADER] = this.token;
    try {
      const res = await fetch(`${this.apiBase}${path}`, {
        method, headers, cache: 'no-store', signal: controller.signal,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const parsed: unknown = await res.json().catch(() => null);
      return { status: res.status, body: parsed, ms: performance.now() - started };
    } finally {
      window.clearTimeout(timeout);
    }
  }

  private async ask(method: string, path: string, body: unknown, done: (b: Record<string, unknown>) => string): Promise<Answer> {
    try {
      const res = await this.call(method, path, body);
      const b = (res.body ?? {}) as Record<string, unknown>;
      if (res.status === 401) this.token = null;
      // The order door answers 200 with ok:false and its reason when it refuses.
      const ok = res.status >= 200 && res.status < 300 && b.ok !== false;
      const status = typeof b.venue === 'string' ? (b as unknown as PhoneStatus) : undefined;
      return { ok, ms: res.ms, text: ok ? done(b) : refusalText(res.status, res.body), status };
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === 'AbortError';
      return { ok: false, ms: TIMEOUT_MS, text: aborted ? 'No answer from Nova in 8 s. Check Orders on the desk before sending again.' : 'Nova could not be reached. Nothing is known to have been sent.' };
    }
  }

  async status(): Promise<PhoneStatus | null> {
    try {
      const res = await this.call('GET', '/api/phone');
      return res.status === 200 ? (res.body as PhoneStatus) : null;
    } catch {
      return null;
    }
  }

  async unlock(pin: string): Promise<Answer> {
    const answer = await this.ask('POST', '/api/phone/unlock', { pin }, (b) => {
      this.token = typeof b.token === 'string' ? b.token : null;
      return 'Unlocked: Paper orders only.';
    });
    return answer;
  }

  lock(): Promise<Answer> {
    return this.ask('POST', '/api/phone/lock', undefined, () => {
      this.token = null;
      return 'Locked.';
    });
  }

  arm(armed: boolean): Promise<Answer> {
    return this.ask('POST', '/api/phone/arm', { armed }, () => (armed ? "Paper's padlock is open." : "Paper's padlock is closed."));
  }

  async order(ctx: OrderContext, side: 'BUY' | 'SELL', qty: number, limitPrice: number | null, intent?: 'flatten'): Promise<Answer> {
    const stamp = orderStamp(ctx, Date.now(), performance.now());
    if (!stamp) return { ok: false, ms: 0, text: "The PC's clock is not measured yet, so the order was not sent. Start the test and wait a second." };
    const body = {
      symbol: ctx.symbol, side, qty,
      order_type: limitPrice == null ? 'MKT' : 'LMT',
      limit_price: limitPrice,
      // A limit may rest outside regular hours; a market order never does.
      outside_rth: limitPrice != null,
      intent,
      idempotency_key: `phone:${ctx.symbol}:${side}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`,
      ...stamp,
    };
    return this.ask('POST', '/api/phone/order', body, (b) =>
      `${intent ? 'Flatten' : side === 'BUY' ? 'Buy' : 'Sell'} ${qty} ${ctx.symbol}: order ${String(b.order_id ?? '?')} ${String(b.broker_status ?? 'accepted')}`);
  }

  async flatten(ctx: OrderContext): Promise<Answer> {
    let rows: unknown;
    try {
      rows = (await this.call('GET', '/api/ibkr/positions')).body;
    } catch {
      return { ok: false, ms: 0, text: 'Your positions could not be read, so nothing was sent.' };
    }
    const row = Array.isArray(rows) ? rows.find((r) => String((r as { symbol?: unknown }).symbol ?? '').toUpperCase() === ctx.symbol) : undefined;
    const close = closingOrder(row as { qty?: unknown; position_side?: unknown } | undefined);
    if (!close) return { ok: false, ms: 0, text: `No ${ctx.symbol} position on Paper to flatten.` };
    // Paper closes at market at any hour (the desk's own flatten ticket on a practice venue).
    return this.order(ctx, close.side, close.qty, null, 'flatten');
  }

  cancelSymbol(symbol: string): Promise<Answer> {
    return this.ask('DELETE', `/api/phone/orders?symbol=${encodeURIComponent(symbol)}`, undefined, (b) => {
      const n = Array.isArray(b.cancelled) ? b.cancelled.length : 0;
      return n ? `Cancelled ${n} working order${n === 1 ? '' : 's'} on ${symbol}.` : `No working orders on ${symbol}.`;
    });
  }
}
