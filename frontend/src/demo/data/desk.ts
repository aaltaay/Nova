/**
 * The desk's own state on the sample morning (ADR 043): health, the IBKR status, the Paper
 * account, orders, a symbol's bars and detail, its news and the diagnostics checklist.
 * Nova Marketing Sample Data. `nowS` is the demo clock, so nothing reads stale.
 */
import {
  NOW_MS, SMPL_DAY_VOLUME, aggregate, etMs, iso, smplDailyBars, smplMinuteBars, tenSecondBars, vwapOf, wireBars, type Bar,
} from './market';
import { SIM_LAST, SIM_PREV_CLOSE, SIM_SYMBOL } from './sim';
import { GAPPERS, ROWS, type ScannerRow } from './universe';

const SMPL_BARS = smplMinuteBars();
const DAYBAR = {
  o: SMPL_BARS[0].o,
  h: Math.max(...SMPL_BARS.map((b) => b.h)),
  l: Math.min(...SMPL_BARS.map((b) => b.l)),
  c: SMPL_BARS[SMPL_BARS.length - 1].c,
  v: SMPL_DAY_VOLUME,
};
export const SMPL = {
  minute: SMPL_BARS,
  five: aggregate(SMPL_BARS, 5),
  fifteen: aggregate(SMPL_BARS, 15),
  ten: tenSecondBars(SMPL_BARS, 45),
  daily: smplDailyBars(DAYBAR),
  vwap: vwapOf(SMPL_BARS),
  last: 4.33,
};

export type Venue = 'paper' | 'sim';

/** The sample row for a symbol; an unknown symbol borrows SMPL's numbers under its own name. */
export function rowFor(symbol: string): ScannerRow {
  return ROWS.get(symbol) ?? { ...GAPPERS[0], symbol };
}

export function health() {
  return {
    status: 'connected', latency_ms: 0, health_source: 'nova_process', latency_source: 'none',
    http_loop_lag_ms: { last_ms: 2, max_ms: 9, samples: 120, wedged: false },
    ib_loop_lag_ms: { last_ms: 3, max_ms: 11, samples: 120, wedged: false },
    integrations: {
      alpaca: { status: 'ok', detail: 'News and listing metadata' },
      ibkr: { status: 'ok', detail: 'Gateway API connected' },
      yfinance: { status: 'ok', detail: 'Fundamentals available' },
    },
  };
}

export function ibkrStatus(venue: Venue, nowS: number) {
  const sim = venue === 'sim';
  const account = sim ? 'NOVA-SIM' : 'NOVA-PAPER';
  return {
    enabled: true, connected: true, transport_connected: true, session_reason: 'ok', session_state: 'ready',
    mode: venue, venue, sim, gateway_mode: 'live', broker_account_kind: 'live',
    account_id: account, account_ids: [account], market_data_type: 1, market_data_delayed: false,
    orders_enabled: true, live_trading_confirmed: false, short_enabled: true, spend_status: 'paper_armed',
    armed: true, armed_by: 'operator', arm_requires_pin: false, live_arm_pin_set: true, armed_for_account_kind: 'paper',
    spend_permitted: true, trading_allowed: true, trading_allowed_reason: null, qty_cap: null,
    preferred_port: 4001, preferred_port_reachable: true, alternate_port: 4002, alternate_port_reachable: false,
    disconnect_hint: null, intentional_gateway_mode: 'live', second_factor_pending: false, second_factor_age_sec: null,
    second_factor_stale: false, completed_orders_unanswered_since: null, gateway_read_only: false, gateway_self_heal: null,
    capture: false, recording: false, capture_symbol: null, capture_symbols: [], capture_sessions: [], capture_resume: [],
    capture_stopped: [], capture_error: null, capture_errors: {},
    leaderboard_recorder: { recording: true, ok: true, error: null, since: nowS - 20_000, run_id: 'lb-2026-09-30' },
    auto_record: null, live_edge: false,
  };
}

const PAPER = {
  venue: 'paper', account_id: 'NOVA-PAPER', starting_cash: 25000, cash: 24505.25, buying_power: 98021.0,
  net_liquidation: 26905.25, gross_position_value: 2400.0, realized_pnl: 1864.25, realized_today: 409.35,
  unrealized_pnl: 41.0, day_pnl: 450.35, day_started_et: '2026-09-30T04:00:00-04:00', commissions_today: 14.5,
  positions: [{ symbol: 'GAPX', qty: 1250, avg_cost: 1.8872, mark: 1.92, unrealized: 41.0 }],
  working: [], fills_today: 7, schema_version: 1, updated_at: '2026-09-30T09:41:26-04:00',
};

/** The practice account; on Sim, the scratch account of the loaded replay. */
export function practiceAccount(venue: Venue) {
  if (venue === 'paper') return PAPER;
  return {
    ...PAPER, venue: 'sim', account_id: 'NOVA-SIM', cash: 25000, buying_power: 100000, net_liquidation: 25000,
    gross_position_value: 0, realized_pnl: 0, realized_today: 0, unrealized_pnl: 0, day_pnl: 0, commissions_today: 0,
    positions: [], fills_today: 0, replay_key: ['capture', 'RUNR', '2026-09-29'],
  };
}

export function ibkrAccount(venue: Venue) {
  const a = practiceAccount(venue);
  return {
    connected: true, mode: venue, venue, account_id: a.account_id, AccountType: 'INDIVIDUAL', account_class: 'margin',
    NetLiquidation: a.net_liquidation, TotalCashValue: a.cash, BuyingPower: a.buying_power,
    AvailableFunds: a.buying_power / 4, GrossPositionValue: a.gross_position_value,
    RealizedPnL: a.realized_today, UnrealizedPnL: a.unrealized_pnl, DayPnL: a.day_pnl, pending: false,
  };
}

export function ibkrPositions(venue: Venue) {
  // ADR 048: a position says its side and where IBKR would liquidate it -- never, for a long paid in full.
  return practiceAccount(venue).positions.map((p) => ({
    symbol: p.symbol, qty: p.qty, market_price: p.mark, market_value: +(p.qty * p.mark).toFixed(2),
    avg_cost: p.avg_cost, commission: 2.5, unrealized_pnl: p.unrealized, realized_pnl: 0, venue,
    position_side: p.qty < 0 ? 'short' : 'long', liquidation_price: null, liquidation_source: null,
  }));
}

function order(id: number, symbol: string, side: string, qty: number, filled: number, type: string, limit: number | null, stop: number | null, avg: number | null, status: string, minAgo: number, extra: Record<string, unknown> = {}) {
  const at = NOW_MS - minAgo * 60_000;
  return {
    order_id: id, source: 'nova', order_source: 'manual', order_origin: null, venue: 'paper', symbol, side, qty,
    filled_qty: filled, remaining_qty: qty - filled, order_type: type, limit_price: limit, stop_price: stop,
    avg_fill_price: avg, fill_estimated: true, fill_basis: 'quote', outside_rth: false, status, tif: 'DAY',
    submitted_at: iso(at), updated_at: iso(at + 900), filled_at: status === 'Filled' ? iso(at + 900) : null,
    commission: status === 'Filled' ? 1.0 : null,
    // ADR 048: what the order does to the position, as a practice row stamps it (the demo's trades are longs).
    short_entry: false, position_side: 'long', effect: side === 'BUY' ? 'opens' : 'closes', ...extra,
  };
}

export const WORKING = [order(7009, 'GAPX', 'SELL', 1250, 0, 'STP', null, 1.82, null, 'Submitted', 4.1, { order_origin: 'nova_exit' })];
const BOT = { order_source: 'bot', order_origin: 'bot' };
export const CLOSED = [
  order(7007, 'GAPX', 'BUY', 1250, 1250, 'LMT', 1.89, null, 1.8872, 'Filled', 4.2),
  order(7006, 'RUNR', 'SELL', 600, 600, 'LMT', 6.74, null, 6.74, 'Filled', 11.7),
  order(7005, 'RUNR', 'BUY', 600, 600, 'LMT', 6.18, null, 6.17, 'Filled', 21.3),
  order(7004, 'SMPL', 'SELL', 10, 10, 'LMT', 4.02, null, 4.02, 'Filled', 37.9, BOT),
  order(7003, 'SMPL', 'BUY', 10, 10, 'LMT', 3.8, null, 3.8, 'Filled', 49.4, BOT),
  order(7002, 'FLTX', 'SELL', 2000, 2000, 'LMT', 0.84, null, 0.84, 'Filled', 94.8),
  order(7001, 'FLTX', 'BUY', 2000, 2000, 'LMT', 0.8, null, 0.8, 'Filled', 103.2),
];

/** A scanner table's envelope, fresh by the demo clock. */
export function envelope(nowS: number, extra: Record<string, unknown>) {
  return {
    rev: '4', mode: 'market', health: health(), data_feed: 'sip', feed_error: null,
    last_scan: nowS - 1, table_state: 'live', roster_ts: nowS - 2, ...extra,
  };
}

const TIMEFRAMES: Record<string, Bar[]> = { '1Min': SMPL.minute, '5Min': SMPL.five, '15Min': SMPL.fifteen, '10Sec': SMPL.ten, '1Day': SMPL.daily };

const DAY_MS = 86_400_000;

/**
 * The Sim replay's candles: SMPL's morning drawn for RUNR the day before, mapped so its prior close
 * and its last sit where the replay's quote says (3.90 and 5.12).
 */
function replayBars(pick: Bar[]): Bar[] {
  const b = (SIM_LAST - SIM_PREV_CLOSE) / (SMPL.last - 2.8);
  const p = (x: number) => +(SIM_PREV_CLOSE + (x - 2.8) * b).toFixed(2);
  return pick.map((x) => ({ ...x, t: x.t - DAY_MS, o: p(x.o), h: p(x.h), l: p(x.l), c: p(x.c) }));
}

/** Bars for a symbol: SMPL is scripted; every other symbol borrows its shape, scaled to its own price. */
export function barsFor(symbol: string, timeframe: string, venue: Venue = 'paper') {
  const pick = TIMEFRAMES[timeframe] ?? SMPL.minute;
  if (venue === 'sim') return symbol === SIM_SYMBOL ? wireBars(replayBars(pick)) : [];
  if (symbol === 'SMPL') return wireBars(pick);
  const k = rowFor(symbol).price / SMPL.last;
  const s = (x: number) => +(x * k).toFixed(x * k < 1 ? 4 : 2);
  return wireBars(pick.map((b) => ({ ...b, o: s(b.o), h: s(b.h), l: s(b.l), c: s(b.c) })));
}

export function tickerDetail(symbol: string) {
  const row = rowFor(symbol);
  const price = symbol === 'SMPL' ? SMPL.last : row.price;
  const prev = row.prev_close;
  const ts = iso(NOW_MS - 600);
  const bar = (o: number, h: number, l: number, c: number, v: number) => ({ open: o, high: h, low: l, close: c, volume: v, trade_count: null, vwap: null, timestamp: null });
  const name = symbol === 'SMPL' ? 'Sample Pharma Inc.' : `${symbol} Sample Co.`;
  return {
    symbol, mode: 'regular', avg_volume: 1_260_000, rel_volume: row.rel_volume, rvol_5min: 9.6, volume_in_5min: 1_320_000,
    news: [], news_impact: null, halt: null,
    asset: { name, exchange: row.exchange, tradable: true, shortable: true, easy_to_borrow: false, marginable: true },
    listing: {
      symbol,
      alpaca: { source: 'alpaca_assets', status: 'active', tradable: true, shortable: true, easy_to_borrow: false, short_type: 'hard_to_borrow', short_type_detail: null, marginable: true, fractionable: false, maintenance_margin_requirement: 30, margin_requirement_long: null, margin_requirement_short: null, asset_class: 'us_equity', exchange: row.exchange, attributes: [], error: null },
      ibkr: { source: 'ibkr', connected: true, qualified: true, con_id: 1, long_name: name, stock_type: 'COMMON', exchange: row.exchange, shortable_shares: 30_000, short_type: 'available', short_type_detail: 'IBKR tick 236 estimate', tradable_hint: 'qualified', error: null, state: 'shortable_est', fetched_at: NOW_MS / 1000 - 20, age_sec: 20, stale: false, ttl_sec: 60, orderable: true },
    },
    snapshot: {
      latest_trade: { price, size: 500, exchange: 'Q', timestamp: ts, source: 'snapshot' },
      latest_quote: { bid_price: +(price - 0.01).toFixed(2), bid_size: 2100, ask_price: price, ask_size: 1900, timestamp: ts },
      minute_bar: null,
      daily_bar: symbol === 'SMPL'
        ? bar(DAYBAR.o, DAYBAR.h, DAYBAR.l, DAYBAR.c, DAYBAR.v)
        : bar(row.open ?? +(prev * 1.05).toFixed(2), +(price * 1.04).toFixed(2), +(prev * 1.01).toFixed(2), price, row.volume),
      prev_daily_bar: bar(+(prev * 0.986).toFixed(2), +(prev * 1.03).toFixed(2), +(prev * 0.96).toFixed(2), prev, 1_180_000),
      prev_close: prev, session_close: null, session_prev_close: null,
    },
    fundamentals: {
      market_cap: row.market_cap, shares_outstanding: row.shares_outstanding, float_shares: row.float,
      short_interest: row.short_interest, short_ratio: row.short_ratio, short_percent_of_float: row.short_interest / row.float,
      pe_ratio: null, forward_pe: null, eps: -0.42, sector: 'Healthcare', industry: 'Biotechnology',
      fifty_two_week_high: +(price * 2.19).toFixed(2), fifty_two_week_low: +(prev * 0.93).toFixed(2), dividend_yield: null, beta: 1.9,
      earnings_date: row.earnings_date, recent_split: null, held_percent_insiders: 0.18, short_interest_ts: row.short_interest_ts,
      float_contradicted: false, float_contradicted_reason: null, short_above_float: false, short_above_float_reason: null,
    },
  };
}

export function catalystsFor(symbol: string) {
  const v = rowFor(symbol).catalyst;
  const items = v ? [
    { item_id: `globenewswire:${symbol}1`, source: 'globenewswire', publisher: v.source, published_ts: v.published_ts, title: v.title, url: v.url, kind: v.verdict === 'negative' ? 'negative' : 'catalyst', category: v.category, strength: v.strength, dilution: v.category === 'dilution' },
    { item_id: `edgar:${symbol}2`, source: 'edgar', publisher: 'SEC EDGAR', published_ts: v.published_ts + 420, title: `8-K: ${v.title}`, url: v.url, kind: 'catalyst', category: v.category, strength: 'weak', dilution: false },
    { item_id: `alpaca:${symbol}3`, source: 'alpaca', publisher: 'Benzinga', published_ts: v.published_ts + 1800, title: `${symbol} shares are trading higher after the company's announcement`, url: v.url, kind: 'noise', category: 'movers_list', strength: null, dilution: false },
  ] : [];
  return { schema_version: 1, symbol, generated_at: NOW_MS / 1000, window_start: etMs(16, 0, 0, '2026-09-29') / 1000, verdict: v, items, items_total: items.length };
}

export function whyFor(symbol: string) {
  const r = rowFor(symbol);
  const news = r.catalyst?.verdict === 'catalyst';
  const check = (id: string, label: string, state: string, value: string, source: string) => ({ id, label, state, value, detail: null, source, as_of: NOW_MS / 1000 });
  return {
    schema_version: 1, symbol, generated_at: NOW_MS / 1000, session_date: '2026-09-30', rules_version: 1,
    likely: news
      ? { kind: 'news', label: 'News', detail: `${r.catalyst?.category.replace(/_/g, ' ')} news this morning: ${r.catalyst?.title}`, confidence: 'likely' }
      : { kind: 'low_float_momentum', label: 'Low-float momentum', detail: 'No news found; a small float trading many times over.', confidence: 'possible' },
    checks: [
      check('news', 'Company news', news ? 'yes' : 'no', r.catalyst ? `${r.catalyst.category.replace(/_/g, ' ')} · ${r.catalyst.strength}` : 'None found', 'Catalyst verdict'),
      check('halts', 'Halts', 'no', 'None today', 'Halt log'),
      check('float', 'Low float', r.float <= 10e6 ? 'yes' : 'no', `${(r.float / 1e6).toFixed(1)}M shares`, 'Yahoo'),
      check('float_rotation', 'Float rotation', r.volume / r.float >= 1 ? 'yes' : 'no', `${(r.volume / r.float).toFixed(1)}x`, 'Volume / float'),
      check('reverse_split', 'Recent reverse split', 'no', 'None in a year', 'Yahoo'),
      check('short_interest', 'Short interest', 'no', `${((r.short_interest / r.float) * 100).toFixed(1)}% of float`, 'FINRA via Yahoo'),
      check('borrow', 'Borrow', 'yes', '18% fee · 30K left', 'IBKR short-stock file'),
      check('volume', 'Relative volume', r.rel_volume >= 5 ? 'yes' : 'no', `${r.rel_volume.toFixed(1)}x`, 'RVOL sensor'),
    ],
    facts: { price: r.price, change_pct: r.change_pct, volume: r.volume, rel_volume: r.rel_volume, float_shares: r.float },
  };
}

type Row = [string, string, string, string, string];
const DIAG_ROWS: Row[] = [
  ['process_identity', 'process', 'API process', 'ok', 'Demo: running in this page'],
  ['process_env_file', 'process', '.env file', 'ok', 'Demo: no keys needed'],
  ['data_folders', 'process', 'Data folders', 'ok', 'Every data folder is on the data drive'],
  ['ibkr_enabled', 'integrations', 'IBKR enabled', 'ok', 'IBKR_ENABLED=true'],
  ['alpaca_keys', 'integrations', 'Alpaca keys', 'ok', 'News and listing metadata'],
  ['finnhub_key', 'integrations', 'Finnhub key', 'off', 'FINNHUB_API_KEY not set (earnings calendar)'],
  ['gateway_port', 'gateway', 'Gateway API port', 'ok', '4001 listening'],
  ['gateway_session', 'gateway', 'Nova session', 'ok', 'ready since 04:00:12 ET'],
  ['market_data_entitlement', 'market_data', 'Entitlement', 'ok', 'live (type 1)'],
  ['market_data_lines', 'market_data', 'Lines held', 'ok', '62 of 100 L1 · 2 of 3 depth'],
  ['ibkr_feed_gaps', 'market_data', 'IBKR feed gaps', 'ok', 'no gaps in the last 30 min'],
  ['market_data_farms', 'market_data', 'IBKR data farms', 'ok', 'all farms OK or idle: secdefnj, usfarm, ushmds'],
  ['leaderboard_recorder', 'recorder', 'Scanner board recorder', 'ok', 'recording since 04:00 · 2.4 TB free'],
  ['tape_archive', 'practice', 'Tape archive', 'ok', 'writing · 0 lost'],
  ['practice_ledger', 'practice', 'Paper ledger', 'ok', 'NOVA-PAPER · $26,905.25'],
  ['frontend_revision', 'frontend', 'UI vs API revision', 'ok', 'one release'],
  ['perf_ib_loop', 'performance', 'IB loop', 'ok', 'worst callback 11 ms in 5 min'],
];

export function diagnostics(nowS: number) {
  return {
    schema_version: 1, generated_at: nowS,
    groups: [
      { id: 'process', title: 'Process' }, { id: 'integrations', title: 'Integrations' }, { id: 'gateway', title: 'Gateway' },
      { id: 'market_data', title: 'Market data' }, { id: 'recorder', title: 'Recorder' }, { id: 'practice', title: 'Practice' },
      { id: 'frontend', title: 'Frontend' }, { id: 'performance', title: 'Performance' },
    ],
    counts: { ok: DIAG_ROWS.filter((r) => r[3] === 'ok').length, warn: 0, fail: 0, off: 1, unknown: 0 },
    process: { pid: 4242, instance_id: 'demo', release_tag: null, checkout_tag: null, repo_root: '<repo>', env_file: '<repo>/.env' },
    rows: DIAG_ROWS.map(([id, group, title, state, detail]) => ({
      id, group, title, state, detail, cause: '', fix: state === 'ok' ? 'Nothing to do.' : 'Optional: add the key to .env.',
      since: null, action: null, evidence: {},
    })),
  };
}

export function captureSessions() {
  const s = (h: number, m: number, day = '2026-09-30') => etMs(h, m, 0, day) / 1000;
  return {
    days: [{ date: '2026-09-30', ticker_count: 2 }, { date: '2026-09-29', ticker_count: 3 }, { date: '2026-09-28', ticker_count: 1 }],
    tickers_by_day: {
      '2026-09-30': [
        { symbol: 'SMPL', prints: 61_342, l2: 182_110, usable: true, empty: false, unavailable_reason: null, segments: 1, missing_sec: 0, last_reason: null, status: 'recording', source: 'ibkr', spans: [[s(7, 1), NOW_MS / 1000]] },
        { symbol: 'GAPX', prints: 18_342, l2: 52_110, usable: true, empty: false, unavailable_reason: null, segments: 2, missing_sec: 0, last_reason: 'operator', status: 'stopped_partial_ok', source: 'ibkr', spans: [[s(7, 40), s(9, 15)], [s(9, 16), s(9, 40)]] },
      ],
      '2026-09-29': [
        { symbol: 'RUNR', prints: 40_211, l2: 120_554, usable: true, empty: false, unavailable_reason: null, segments: 2, missing_sec: 42, last_reason: 'operator', status: 'stopped_partial_ok', source: 'ibkr', spans: [[s(7, 2, '2026-09-29'), s(9, 58, '2026-09-29')], [s(9, 59, '2026-09-29'), s(11, 30, '2026-09-29')]] },
        { symbol: 'SPIK', prints: 22_904, l2: 61_330, usable: true, empty: false, unavailable_reason: null, segments: 1, missing_sec: 0, last_reason: 'auto', status: 'stopped_partial_ok', source: 'ibkr', spans: [[s(7, 10, '2026-09-29'), s(10, 0, '2026-09-29')]] },
      ],
    },
  };
}
