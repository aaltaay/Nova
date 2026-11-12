/**
 * A stand-in for Nova's API, for the phone's screens (ADR 070). The phone page served from the test's
 * own Vite server talks to `http://127.0.0.1:8000`, which on the operator's PC is the live desk: every
 * request to it is answered here and none is let through. All of it is Nova Marketing Sample Data.
 *
 * It keeps the door's little state (the PIN's session, the padlock, the working orders), records every
 * request that is not a GET, and names any path it has no answer for.
 */
import type { Page } from '@playwright/test';

export const PHONE_API = 'http://127.0.0.1:8000';
export const PHONE_PIN = '246810';
const TOKEN = 'sample-session-token';

const SYMBOLS = [
  'ABCD', 'WXYZ', 'QRST', 'LMNO', 'EFGH', 'IJKL', 'UVWX', 'MNOP', 'CDEF', 'GHIJ', 'KLMN', 'OPQR',
  'STUV', 'YZAB', 'BCDE', 'FGHI', 'JKLM', 'NOPQ', 'RSTU', 'VWXY',
];

/** A sample ticker for place `i`, never the same twice on one list. */
function sampleSymbol(i: number): string {
  if (i < SYMBOLS.length) return SYMBOLS[i];
  const n = i - SYMBOLS.length;
  return `S${String.fromCharCode(65 + (n % 26))}${String.fromCharCode(65 + Math.floor(n / 26))}X`;
}

function catalyst(kind: 'catalyst' | 'none_found', nowSec: number, i: number) {
  return {
    verdict: kind, category: kind === 'catalyst' ? 'company_news' : null, strength: kind === 'catalyst' ? 'strong' : null,
    title: kind === 'catalyst' ? `[Sample headline ${i + 1}]` : null, source: kind === 'catalyst' ? 'globenewswire' : null,
    published_ts: kind === 'catalyst' ? nowSec - (9 + i * 13) * 60 : null, url: kind === 'catalyst' ? 'https://example.test/news' : null,
    negative_too: false, rules_version: 'sample',
  };
}

function rows(count: number, nowSec: number, start = 0) {
  return Array.from({ length: count }, (_, i) => {
    const prev = 1 + i * 0.37;
    const change = 0.382 - i * 0.017;
    return {
      symbol: sampleSymbol(start + i), rank: i + 1, exchange: 'NASDAQ',
      price: Number((prev * (1 + change)).toFixed(2)), prev_close: Number(prev.toFixed(2)),
      change_pct: change, change_abs: Number((prev * change).toFixed(2)), gap_percent: change * 0.6,
      volume: 2_100_000 - i * 61_000, rel_volume: 14.2 - i * 0.6, float: 4_200_000 + i * 900_000,
      market_cap: 48_000_000, short_interest: null, short_ratio: null,
      has_news: i % 2 === 0, newest_headline_at: null, halted: i === 2,
      catalyst: catalyst(i % 2 === 0 ? 'catalyst' : 'none_found', nowSec, i),
    };
  });
}

function envelope(nowSec: number, extra: Record<string, unknown>) {
  return {
    rev: 'sample', mode: 'market', data_feed: 'ibkr', feed_error: null,
    health: { status: 'ok', latency_ms: 1 }, last_scan: nowSec, table_state: 'live', roster_ts: nowSec, ...extra,
  };
}

function dayRead() {
  const check = (id: string, label: string, state: string, text: string) => ({ id, label, state, value: null, text, starts_at: null, why: null });
  return {
    verdict: 'bullish', green: 4, red: 1, known: 6, total: 6,
    temperature: { day: 'warm', week: 'good', month: 'warm' },
    checks: [
      check('runners', 'Small-cap runners above normal', 'green', '129 vs 80 avg'),
      check('gappers', 'Gappers holding their open', 'green', '9 of 11'),
      check('small_caps', 'Small caps lagging large caps', 'red', '-0.38 pt'),
      check('futures', 'Futures up across the board', 'green', '4 of 4 up'),
      check('breadth', 'Breadth: advancers vs decliners', 'amber', '1.1 : 1'),
      check('vix', 'Fear gauge falling (VIX)', 'green', '17.49'),
    ],
  };
}

function bars(nowSec: number, count = 120) {
  const out = [];
  let price = 4.1;
  for (let i = count; i >= 1; i -= 1) {
    const open = price;
    price = Math.max(0.5, open + Math.sin(i / 4) * 0.03 + 0.006);
    out.push({
      t: new Date((Math.floor(nowSec / 60) * 60 - i * 60) * 1000).toISOString(),
      o: Number(open.toFixed(4)), h: Number((Math.max(open, price) + 0.02).toFixed(4)),
      l: Number((Math.min(open, price) - 0.02).toFixed(4)), c: Number(price.toFixed(4)), v: 8_000 + (i % 7) * 2_500,
    });
  }
  return out;
}

export interface PhoneApiOptions {
  /** Working orders at the start, by id. */
  working?: number;
  positions?: number;
  pinSet?: boolean;
  venue?: 'paper' | 'sim' | 'live';
  /** The Level 2 the Trade screen gets: live (the default), or every frame 1.4 s old when it arrives. */
  book?: 'live' | 'behind';
  /** The padlock when the page opens (locked by default, as after a backend start). */
  armed?: boolean;
  /** Your shares of the first symbol when the page opens; negative is a short opened on the desk. Default 500. */
  held?: number;
}

/** One order as the Trade screen sent it to `POST /api/phone/order`. */
export interface SentOrder {
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  order_type: string;
  limit_price?: number | null;
  stop_price?: number | null;
  reference_price?: number | null;
  outside_rth?: boolean;
  intent?: string | null;
  view?: { instance?: string | null; book?: { seq: number; bid: number | null; ask: number | null } | null; action_wall_ms?: number };
  client_timing?: Record<string, number>;
}

export interface PhoneApi {
  /** Every request that was not a GET, as "METHOD /path". */
  writes: string[];
  /** Every path asked for, whatever the method. */
  asked: string[];
  /** Paths this stand-in had no answer for. */
  unanswered: string[];
  /** Every order the Trade screen sent, in order. */
  orders: SentOrder[];
  /** Every cancel-many the screen sent: the query it carried. */
  cancels: string[];
  /**
   * `accountDown`: the account, positions and orders reads fail from now on, as when the Gateway or the ledger drops.
   * `held`: your shares of the first symbol; an order that fills moves it, as the ledger would.
   */
  state: { armed: boolean; unlocked: boolean; working: number[]; accountDown: boolean; held: number };
}

const BID = 4.81;
const ASK = 4.82;
const BIDS: readonly [string, number, number][] = [['NSDQ', 4.81, 1200], ['ARCA', 4.81, 800], ['EDGX', 4.81, 300], ['BATS', 4.80, 3400], ['NSDQ', 4.80, 1000], ['ARCA', 4.79, 900], ['NYSE', 4.79, 500], ['EDGX', 4.79, 200], ['NSDQ', 4.78, 5000], ['BATS', 4.78, 700], ['ARCA', 4.77, 700], ['NSDQ', 4.77, 400], ['EDGX', 4.76, 2200], ['BATS', 4.75, 600], ['NSDQ', 4.74, 900]];
const ASKS: readonly [string, number, number][] = [['ARCA', 4.82, 800], ['NSDQ', 4.82, 500], ['EDGX', 4.83, 2100], ['BATS', 4.83, 600], ['NSDQ', 4.83, 200], ['ARCA', 4.84, 500], ['NSDQ', 4.85, 6300], ['NYSE', 4.85, 1100], ['EDGX', 4.85, 400], ['BATS', 4.86, 1000], ['ARCA', 4.86, 300], ['NSDQ', 4.87, 400], ['EDGX', 4.88, 3900], ['BATS', 4.89, 500], ['NSDQ', 4.90, 800]];

export async function mockPhoneApi(page: Page, opts: PhoneApiOptions = {}): Promise<PhoneApi> {
  const api: PhoneApi = {
    writes: [],
    asked: [],
    unanswered: [],
    orders: [],
    cancels: [],
    state: {
      armed: opts.armed ?? false, unlocked: false, working: Array.from({ length: opts.working ?? 1 }, (_, i) => 7 + i), accountDown: false,
      held: opts.held ?? ((opts.positions ?? 2) > 0 ? 500 : 0),
    },
  };
  const venue = opts.venue ?? 'paper';
  const pinSet = opts.pinSet ?? true;
  const nowSec = () => Date.now() / 1000;
  const status = (token: string | null) => ({
    schema_version: 1, pin_set: pinSet, unlocked: api.state.unlocked && token === TOKEN,
    expires_at: api.state.unlocked && token === TOKEN ? nowSec() + 7 * 3600 + 12 * 60 : null,
    venue, paper: venue === 'paper', armed: api.state.armed, now: nowSec(),
  });
  const others = Array.from({ length: Math.max(0, (opts.positions ?? 2) - 1) }, (_, k) => {
    const i = k + 1;
    return {
      symbol: SYMBOLS[i], qty: 500 - i * 200, market_price: 4.82 - i * 2.65, market_value: 2410, avg_cost: 4.71 - i * 2.66,
      unrealized_pnl: 55 - i * 19, realized_pnl: 0, position_side: 'long',
    };
  });
  /** Your rows now: the first symbol follows `state.held`. */
  const positionsNow = () => [
    ...(api.state.held ? [{
      symbol: SYMBOLS[0], qty: api.state.held, market_price: 4.82, market_value: api.state.held * 4.82, avg_cost: 4.71,
      unrealized_pnl: Math.round(api.state.held * 0.11), realized_pnl: 0, position_side: api.state.held < 0 ? 'short' : 'long',
    }] : []),
    ...others,
  ];
  let nextOrderId = 40;
  const order = (id: number) => ({
    order_id: id, symbol: SYMBOLS[0], side: 'SELL', qty: 250, remaining_qty: 250, order_type: 'LMT', limit_price: 4.95,
    status: 'Submitted', venue, owner: 'you', outside_rth: true,
  });

  await page.route(`${PHONE_API}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();
    api.asked.push(path);
    const json = (body: unknown, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(body) });
    const refuse = (code: number, reason: string, error: string) => json({ detail: { reason, error } }, code);
    const token = req.headers()['x-nova-phone-session'] ?? null;
    const t = nowSec();

    if (method !== 'GET') {
      api.writes.push(`${method} ${path}`);
      if (path === '/api/phone/unlock') {
        const pin = (req.postDataJSON() as { pin?: string } | null)?.pin;
        if (pin !== PHONE_PIN) return refuse(403, 'PHONE_PIN_INVALID', 'That is not the phone PIN.');
        api.state.unlocked = true;
        return json({ token: TOKEN, ...status(TOKEN) });
      }
      if (!path.startsWith('/api/phone')) return refuse(403, 'REMOTE_VIEW_ONLY', 'Nova is view-only from another device');
      if (!api.state.unlocked || token !== TOKEN) return refuse(401, 'PHONE_LOCKED', 'Unlock with your phone PIN first. Nothing was sent.');
      if (path === '/api/phone/lock') {
        api.state.unlocked = false;
        return json(status(null));
      }
      if (path === '/api/phone/arm') {
        api.state.armed = (req.postDataJSON() as { armed?: boolean } | null)?.armed === true;
        return json(status(token));
      }
      if (path === '/api/phone/order' && method === 'POST') {
        const body = req.postDataJSON() as SentOrder;
        api.orders.push(body);
        // The padlock holds everything but a Flatten, as the desk's arm latch does.
        if (!api.state.armed && body.intent !== 'flatten') {
          return json({ ok: false, order_id: null, error: 'The desk is locked: open the padlock to send orders.', reason_code: 'DISARMED' });
        }
        nextOrderId += 1;
        const rests = body.order_type === 'STP' || (body.order_type === 'LMT' && body.side === 'SELL' && (body.limit_price ?? 0) >= ASK)
          || (body.order_type === 'LMT' && body.side === 'BUY' && (body.limit_price ?? 0) < ASK);
        if (rests) api.state.working = [...api.state.working, nextOrderId];
        else api.state.held += body.side === 'BUY' ? body.qty : -body.qty;
        return json({ ok: true, order_id: nextOrderId, broker_status: rests ? 'Submitted' : 'Filled' });
      }
      if (path === '/api/phone/orders' && method === 'DELETE') {
        api.cancels.push(url.search);
        const cancelled = api.state.working;
        api.state.working = [];
        return json({ ok: true, cancelled, failed: [], error: null });
      }
      const cancel = /^\/api\/phone\/order\/(\d+)$/.exec(path);
      if (cancel && method === 'DELETE') {
        api.state.working = api.state.working.filter((id) => id !== Number(cancel[1]));
        return json({ ok: true, order_id: Number(cancel[1]) });
      }
      return refuse(404, 'NOT_FOUND', 'No such route.');
    }

    if (api.state.accountDown && /^\/api\/(practice\/account|ibkr\/(account|positions|orders))/.test(path)) {
      return json({ detail: 'The ledger did not answer.' }, 500);
    }

    switch (path) {
      case '/api/phone': return json(status(token));
      case '/api/config': return json({ discovery_provider: 'ibkr', data_feed: 'ibkr', scanner_persistent_enabled: true, scanner_persistent_authoritative: true });
      case '/api/ibkr/status': return json({
        connected: true, transport_connected: true, session: 'ready', mode: venue, venue, armed: api.state.armed,
        spend_status: api.state.armed ? `${venue}_armed` : 'locked_disarmed', arm_requires_pin: venue === 'live',
        gateway_mode: 'live', broker_account_kind: 'live', trading_allowed: true,
      });
      case '/api/gappers': return json(envelope(t, { gappers: rows(34, t) }));
      case '/api/movers': return json(envelope(t, { gainers: rows(27, t, 3), losers: rows(8, t, 9) }));
      case '/api/afterhours': return json(envelope(t, { afterhours: [] }));
      case '/api/large-cap': return json(envelope(t, { large_cap: rows(5, t, 12) }));
      case '/api/news-catalysts': return json(envelope(t, { catalysts: [] }));
      case '/api/scan/envelope': return json(envelope(t, { tables: {} }));
      case '/api/history/dates': return json({ dates: [] });
      case '/api/market/board': return json({
        schema_version: 1, generated_at: t, enabled: true, loading: false, replay_desk: false,
        session: { date: '2026-11-11', phase: 'regular', open_at: t - 60, close_at: t + 3600, next: null, holiday: null },
        day_read: dayRead(), events: { bond_market: { closed: false, why: null }, today: [], upcoming: [] },
        quotes: [], breadth: {}, sectors: {}, industries: {}, climate: null, top: {}, sources: [],
      });
      case '/api/practice/account': return json({
        schema_version: 1, venue, account_id: 'SAMPLE', starting_cash: 25_000, cash: 22_640, buying_power: 22_640,
        net_liquidation: 25_412.6, gross_position_value: 2_772.6, realized_pnl: 321.6, unrealized_pnl: 91, unrealized_at_bid: 88,
        day_pnl: 412.6, realized_today: 321.6, commissions_today: 8.4, fills_today: 6, day_started_et: '2026-11-11T04:00:00-05:00',
        updated_at: new Date().toISOString(),
        positions: positionsNow().map((p, i) => ({
          symbol: p.symbol, qty: p.qty, avg_cost: p.avg_cost, market_price: p.market_price, market_value: p.market_value,
          unrealized_pnl: p.unrealized_pnl,
          by_owner: [{ owner: i ? 'bots' : 'you', bot: i ? 'first_pullback' : null, qty: p.qty, avg_cost: p.avg_cost, unrealized_pnl: p.unrealized_pnl }],
        })),
        working: api.state.working.map(order),
        books: {
          you: { day_pnl: 376.6, realized_today: 321.6, unrealized_pnl: 55, fills_today: 4, commissions_today: 6.4 },
          bots: { day_pnl: 36, realized_today: 0, unrealized_pnl: 36, fills_today: 2, commissions_today: 2, budget_usd: 25_000, budget_used_usd: 615, by_bot: {} },
        },
      });
      case '/api/practice/history': return json({
        schema_version: 1, venue, account_id: 'SAMPLE', range: '1D', range_start: t - 6 * 3600, starting_cash: 25_000,
        ledger_opened_at: '2026-11-01T04:00:00-05:00',
        equity: Array.from({ length: 6 }, (_, i) => ({
          ts: t - (6 - i) * 1800, net_liquidation: 25_000 + i * 70, cash: 22_640, realized: i * 64, unrealized: i * 6,
        })),
        fills: Array.from({ length: 6 }, (_, i) => ({
          ts: t - (6 - i) * 1800, order_id: 100 + i, symbol: SYMBOLS[i % 3], side: i % 2 ? 'SELL' : 'BUY', qty: 250, price: 4.7 + i * 0.03,
          source: 'manual', bot_id: null, commission: 1.4, fees: 0, realized: i % 2 ? 64 : 0, fill_estimated: true, fill_basis: 'quote',
          owner: 'you', bot: null, parts: [],
        })),
        by_source: [], by_owner: [], daily: [],
        components: { realized: 321.6, commissions: 8.4, fees: 0 },
      });
      case '/api/ibkr/account': return json({ NetLiquidation: 25_412.6, BuyingPower: 22_640, RealizedPnL: 321.6, UnrealizedPnL: 91 });
      case '/api/ibkr/positions': return json(positionsNow());
      case '/api/ibkr/orders': return json(api.state.working.map(order));
      case '/api/ibkr/orders/closed': return json([]);
      case '/api/loss-limit': return json({
        schema_version: 1, day: '2026-11-11', until: t + 3600, error: null,
        settings: { limit_usd: 300, you_usd: null, bots_usd: null, warn: true, no_new_buys: true, auto_sell: false, set_at: null, source: 'operator', error: null },
        accounts: { [venue]: { name: venue, counted_at: t, pnl: 412.6, loss: 0, unknown: null, lines: { account: { on: true, pnl: 412.6, loss: 0, warned_at: null, warned_loss: null, tripped_at: null, tripped_loss: null, limit_usd: null, sold: null, sell_error: null, no_new_buys: null } } } },
      });
      case '/api/hot-list': return json({
        schema_version: 1, date: '2026-11-11', cap: 10, auto_cap: 10, auto: { n: 3, start: '04:00', end: '16:00', rule: null, error: null },
        entries: [{ symbol: 'ABCD', how: 'star', at: t - 600, board: 'gappers', rank: 1, change_pct: 0.382, followed: true, why_not_followed: null }],
        yesterday: [], error: null,
      });
      default:
    }
    if (/^\/api\/ticker\/[A-Z.]+\/bars$/.test(path)) return json({ bars: bars(t) });
    // The lines drawn on the desk's chart: none on the stand-in.
    if (/^\/api\/chart-drawings\/[A-Z.]+$/.test(path)) return json({ drawings: [] });
    // An API from before the batch Catalyst read: the phone falls back to each row's own news verdict.
    if (path === '/api/why') return json({ detail: 'Not Found' }, 404);
    api.unanswered.push(path);
    return json({ detail: 'Not Found' }, 404);
  });

  // The scanner's rows came by REST; its socket stays open and silent, as on a quiet tape.
  await page.routeWebSocket(/127\.0\.0\.1:8000\/ws\/(?!ticker\/|ibkr\/(depth|tape)\/)/, () => undefined);
  // Level 2: the desk's depth socket. `behind`: every frame says it was sent 1.4 s before it arrives.
  const late = opts.book === 'behind' ? 1.4 : 0;
  await page.routeWebSocket(/127\.0\.0\.1:8000\/ws\/ibkr\/depth\//, (socket) => {
    const symbol = decodeURIComponent(new URL(socket.url()).pathname.split('/').pop() ?? '').toUpperCase();
    const level = (side: 'bid' | 'ask') => ([mm, price, size]: readonly [string, number, number]) => ({ mm, price, size, side });
    socket.send(JSON.stringify({ type: 'subscribed', symbol, instance: 'stand-in-backend' }));
    socket.send(JSON.stringify({
      type: 'book', symbol, seq: 4, at: nowSec() - late, sent: nowSec() - late,
      data: { bids: BIDS.map(level('bid')), asks: ASKS.map(level('ask')), l1_fallback: false },
    }));
    const beat = setInterval(() => socket.send(JSON.stringify({ type: 'beat', symbol, seq: 4, now: nowSec() - late })), 250);
    socket.onClose(() => clearInterval(beat));
  });
  await page.routeWebSocket(/127\.0\.0\.1:8000\/ws\/ibkr\/tape\//, (socket) => {
    const symbol = decodeURIComponent(new URL(socket.url()).pathname.split('/').pop() ?? '').toUpperCase();
    socket.send(JSON.stringify({ type: 'subscribed', symbol }));
    if (opts.book === 'behind') return;
    const sizes = [500, 200, 1000, 300, 100, 700, 400, 2500, 100, 600, 300, 900, 200, 500, 800, 150];
    socket.send(JSON.stringify({
      type: 'prints', symbol,
      // Oldest first, as the socket sends a batch.
      items: sizes.map((size, i) => {
        const at = Date.now() - (sizes.length - i) * 700;
        const up = i % 3 !== 2;
        return { symbol, time: new Date(at).toISOString(), exchange_ts: Math.floor(at / 1000), price: up ? ASK : BID, size, exchange: 'Q', side: up ? 'ask' : 'bid', bid: BID, ask: ASK };
      }),
    }));
    const ping = setInterval(() => socket.send(JSON.stringify({ type: 'ping', symbol, gate: null })), 1000);
    socket.onClose(() => clearInterval(ping));
  });
  await page.routeWebSocket(/127\.0\.0\.1:8000\/ws\/ticker\//, (socket) => {
    const symbol = decodeURIComponent(new URL(socket.url()).pathname.split('/').pop() ?? '').toUpperCase();
    socket.send(JSON.stringify({
      type: 'initial', symbol, mode: 'market', asset: { name: 'Sample Co', exchange: 'NASDAQ' },
      snapshot: {
        latest_trade: { price: 4.82, size: 100, timestamp: new Date().toISOString(), exchange: 'Q' },
        latest_quote: { bid_price: 4.81, bid_size: 12, ask_price: 4.82, ask_size: 8, timestamp: new Date().toISOString() },
        daily_bar: { open: 4.2, high: 4.84, low: 3.41, close: 4.82, volume: 2_100_000, trade_count: null, vwap: null, timestamp: null },
        prev_close: 3.49, prev_daily_bar: null,
      },
      avg_volume: 148_000, rel_volume: 14.2, news: [
        { headline: '[Sample headline, one line]', summary: '', author: '', source: 'Sample Wire', url: 'https://example.test/news', created_at: new Date(Date.now() - 9 * 60_000).toISOString(), symbols: [symbol], images: [] },
      ],
      fundamentals: { market_cap: 48_000_000, shares_outstanding: 10_000_000, float_shares: 4_200_000, short_interest: null, short_ratio: null, short_percent_of_float: 0.182 },
      halt: null,
    }));
  });
  return api;
}

/**
 * What must never be true of a phone screen: the page scrolls, or something sits past an edge, or text
 * is cut without an ellipsis. Returns one line per problem. The desk chart's own canvas is not judged.
 */
export async function phoneOverflow(page: Page): Promise<string[]> {
  const size = page.viewportSize();
  if (!size) return ['no viewport'];
  return page.evaluate(([vw, vh]) => {
    const bad: string[] = [];
    const doc = document.scrollingElement;
    if (doc && (doc.scrollHeight > vh + 1 || doc.scrollWidth > vw + 1)) bad.push(`the page scrolls: ${doc.scrollWidth}x${doc.scrollHeight}`);
    for (const el of document.querySelectorAll<HTMLElement>('.ph-root *, .ph-sheet *')) {
      if (el.closest('svg') || el.closest('.chart-body') || el.closest('.chart-oscillators')) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const label = `${String(el.className).slice(0, 40)} "${(el.innerText || '').slice(0, 24).replace(/\n/g, ' ')}"`;
      if (r.right > vw + 0.5 || r.bottom > vh + 0.5 || r.left < -0.5 || r.top < -0.5) bad.push(`off-screen: ${label}`);
      const cs = getComputedStyle(el);
      if (cs.textOverflow !== 'ellipsis' && cs.display !== 'inline' && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1) bad.push(`cut off: ${label}`);
    }
    return bad;
  }, [size.width, size.height]);
}
