/**
 * Page-level Nova Marketing Sample Data (ADR 043): the Paper ledger's history, the bot session,
 * the setups board and the per-stock modes. Every figure reconciles with the account in desk.ts:
 * today's net realized 409.35 + open 41.00 = the day's 450.35; lifetime net realized 1,864.25.
 */
import { DAY, NOW_S, etMs, r2 } from './market';

const at = (h: number, m: number, s = 0) => etMs(h, m, s) / 1000;

function fill(ts: number, order_id: number, symbol: string, side: string, qty: number, price: number, source: string, bot_id: string | null, commission: number, fees: number, realized: number) {
  return { ts, order_id, symbol, side, qty, price, source, bot_id, commission, fees, realized, fill_estimated: true, fill_basis: 'quote' };
}

/** Today's fills; net realized per fill = gross P&L - its commission - its fees. */
const FILLS_TODAY = [
  fill(at(7, 58, 12), 7001, 'FLTX', 'BUY', 2000, 0.8, 'manual', null, 2.0, 0, -2.0),
  fill(at(8, 6, 40), 7002, 'FLTX', 'SELL', 2000, 0.84, 'manual', null, 2.0, 0.15, 77.85),
  fill(at(8, 52, 3), 7003, 'SMPL', 'BUY', 10, 3.8, 'bot', 'nova-first-pullback', 1.0, 0, -1.0),
  fill(at(9, 3, 31), 7004, 'SMPL', 'SELL', 10, 4.02, 'bot', 'nova-first-pullback', 1.0, 0.02, 1.18),
  fill(at(9, 20, 8), 7005, 'RUNR', 'BUY', 600, 6.17, 'manual', null, 3.0, 0, -3.0),
  fill(at(9, 29, 44), 7006, 'RUNR', 'SELL', 600, 6.74, 'manual', null, 3.0, 0.18, 338.82),
  fill(at(9, 37, 15), 7007, 'GAPX', 'BUY', 1250, 1.8872, 'manual', null, 2.5, 0, -2.5),
];
const REALIZED_TODAY = r2(FILLS_TODAY.reduce((s, f) => s + f.realized, 0));
const LIFETIME_REALIZED = 1864.25;
const STARTING_CASH = 25_000;

// September's practice days before today (Labor Day closed): [date, net realized, fills].
const PRIOR: [string, number, number][] = [
  ['2026-09-01', 128.4, 9], ['2026-09-02', -64.2, 6], ['2026-09-03', 210.75, 11], ['2026-09-04', 86.1, 7],
  ['2026-09-08', -121.5, 8], ['2026-09-09', 54.3, 5], ['2026-09-10', 176.9, 10], ['2026-09-11', -38.25, 4],
  ['2026-09-14', 92.6, 6], ['2026-09-15', 144.2, 9], ['2026-09-16', -88.7, 7], ['2026-09-17', 63.15, 5],
  ['2026-09-18', 205.4, 12], ['2026-09-21', -52.9, 6], ['2026-09-22', 118.35, 8], ['2026-09-23', 71.8, 5],
  ['2026-09-24', -96.4, 9], ['2026-09-25', 149.6, 10], ['2026-09-28', 33.85, 4], ['2026-09-29', 0, 8],
];
// The last prior day settles the lifetime total exactly.
PRIOR[PRIOR.length - 1][1] = r2(LIFETIME_REALIZED - REALIZED_TODAY - PRIOR.slice(0, -1).reduce((s, d) => s + d[1], 0));

const sum = <T extends Record<K, number>, K extends string>(xs: T[], k: K) => r2(xs.reduce((s, x) => s + x[k], 0));

export function practiceHistory(range: string, venue: string) {
  const dayClose = (d: string) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10), 20, 0) / 1000;
  const isDay = range === '1D';
  const point = (ts: number, realized: number) => ({ ts, net_liquidation: r2(STARTING_CASH + realized), cash: r2(STARTING_CASH + realized), realized, unrealized: 0 });
  const equity = [];
  let realized = 0;
  if (isDay) {
    realized = r2(LIFETIME_REALIZED - REALIZED_TODAY);
    equity.push(point(at(4, 0), realized));
  } else {
    equity.push(point(Date.UTC(2026, 7, 31, 20, 0) / 1000, 0));
    for (const [d, r] of PRIOR) {
      realized = r2(realized + r);
      equity.push(point(dayClose(d), realized));
    }
  }
  for (const f of FILLS_TODAY) {
    realized = r2(realized + f.realized);
    equity.push(point(f.ts, realized));
  }
  const manual = FILLS_TODAY.filter((f) => f.source === 'manual');
  const bot = FILLS_TODAY.filter((f) => f.source === 'bot');
  return {
    venue, account_id: venue === 'sim' ? 'NOVA-SIM' : 'NOVA-PAPER', range,
    range_start: isDay ? at(4, 0) : Date.UTC(2026, 8, 1, 8) / 1000,
    schema_version: 1, starting_cash: STARTING_CASH, ledger_opened_at: '2026-08-31T16:00:00-04:00',
    equity,
    fills: FILLS_TODAY,
    by_source: isDay
      ? [
        { source: 'manual', bot_id: null, realized: sum(manual, 'realized'), fills: manual.length, commissions: sum(manual, 'commission'), fees: sum(manual, 'fees') },
        { source: 'bot', bot_id: 'nova-first-pullback', realized: sum(bot, 'realized'), fills: bot.length, commissions: sum(bot, 'commission'), fees: sum(bot, 'fees') },
      ]
      : [
        { source: 'manual', bot_id: null, realized: r2(LIFETIME_REALIZED - 46.2), fills: 142, commissions: 246.1, fees: 6.9 },
        { source: 'bot', bot_id: 'nova-first-pullback', realized: 46.2, fills: 18, commissions: 18.0, fees: 0.4 },
      ],
    daily: [
      ...PRIOR.map(([date, r, n]) => ({ date, realized: r, commissions: r2(n * 1.6), fees: r2(n * 0.05), fills: n, archived: false })),
      { date: DAY, realized: REALIZED_TODAY, commissions: 14.5, fees: 0.35, fills: FILLS_TODAY.length, archived: false },
    ],
    archives: [],
    components: isDay
      ? { realized: REALIZED_TODAY, unrealized: 41.0, commissions: 14.5, sec_finra_fees: 0.35, bot_realized: sum(bot, 'realized') }
      : { realized: LIFETIME_REALIZED, unrealized: 41.0, commissions: 264.1, sec_finra_fees: 7.3, bot_realized: 46.2 },
    warnings: [],
  };
}

const gate = (id: string, stage: string, detail: Record<string, unknown> = {}) => ({ id, ok: true, stage, detail });
const caps = (venue: string) => ({
  venue, risk_usd: 50, max_shares: 10, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: true,
  entries_per_day: 3, api_kinds: [], allowlist: [],
});
const PAIR = { soft_usd: -50, hard_usd: -200 };

export function botSession(nowS: number, venue: string) {
  return {
    level: 2, level_venue: venue, levels_by_venue: { paper: 2, sim: 1, live: 0 },
    active: true, armed: true, has_desk_arm: true, deactivated: null,
    setups: [
      { id: 'first_pullback', scanner: true, level: 2, effective: 2 },
      { id: 'bull_flag', scanner: true, level: 1, effective: 1 },
      { id: 'flat_top_breakout', scanner: true, level: 1, effective: 1 },
      { id: 'red_to_green', scanner: true, level: 0, effective: 0 },
      { id: 'gap_and_go', scanner: false, level: null, effective: null },
      { id: 'micro_pullback', scanner: false, level: null, effective: null },
    ],
    setup_levels: { first_pullback: 2, bull_flag: 1, flat_top_breakout: 1, red_to_green: 0 },
    ready: true, ready_reason: null, live_fire_ready: true,
    gates: [
      gate('venue', 'activate', { venue, live_edge: false, text: null }),
      gate('level', 'activate', { level: 2 }),
      gate('setups', 'activate', { at_strategy: ['first_pullback'] }),
      gate('padlock', 'activate', { reason: null }),
      gate('allowlist', 'fire', { count: 3, auto_entry: 0 }),
      gate('bot_trip', 'activate', { fired_at: null, pnl: null, until: null }),
      gate('depth_lines', 'fire', { held: ['SMPL', 'GAPX'], missing: [], max_lines: 3 }),
      gate('day_lock', 'fire', { until: null, tripped_at: null, pnl: null, venue }),
      gate('kill_switch', 'fire'),
      gate('window', 'fire', { setups: [{ setup: 'first_pullback', start: '07:00', end: '11:30', open: true, clipped: false }], venue_time: null }),
      gate('daily_cap', 'fire', { count: 1, cap: 3, venue_day: DAY }),
      gate('extended_hours', 'fire'),
      gate('commissions', 'fire'),
    ],
    breakers: {
      venue, ...PAIR, custom: false, defaults: { ...PAIR },
      by_venue: { live: { ...PAIR }, paper: { ...PAIR }, sim: { ...PAIR } },
      bounds: { soft_usd: [-1000, -5], hard_usd: [-5000, -10], step_usd: 5 }, note: null,
    },
    runner: { brain_id: 'nova-first-pullback', playing: true, reason: null },
    trade: {
      setup_id: 'SMPL-2026-09-30-0834', setup_type: 'first_pullback', symbol: 'SMPL', venue: 'paper', venue_day: DAY,
      template_id: 'default', template_rev: 1, state: 'closed', qty: 10, trigger: 3.79, entry_planned: 3.8, stop: 3.69,
      target1: 4.02, risk: 0.11, entry_order_id: 7003, entry_fill_price: 3.8, entry_filled_ts: at(8, 52, 3),
      target_order_id: 7004, stop_order_id: 7016, stop_leg_at: null, exit_order_id: 7004, exit_price: 4.02, exit_reason: 'target',
      exit_why: null, closed_ts: at(9, 3, 31), slippage: 0, r: 2.0, size_text: '10 shares (max shares)', waiting: null, note: null,
    },
    symbol_allowlist: ['SMPL', 'GAPX', 'RUNR'],
    caps: caps(venue),
    caps_bounds: { risk_usd: [1, 10000], max_shares: [1, 10], bp_budget_usd: [0.01, 50], working_ttl_sec: [1, 10], entries_per_day: [1, 3] },
    caps_by_venue: { paper: caps('paper'), sim: caps('sim'), live: caps('live') },
    entries_today: {
      count: 1, cap: 3, venue_day: DAY,
      entries: [{ symbol: 'SMPL', setup_type: 'first_pullback', by: 'bot', ts: at(8, 52, 3), outcome: 'filled' }], approved: 0,
    },
    day_lock: { active: false, until: null, tripped_at: null, pnl: null, venue, threshold: -200, text: null },
    day_locks: {},
    soft_breaker: { fired: false, at: null, pnl: null, until: null },
    soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
    brain_session_id: 'nova-first-pullback', brain_heartbeat_ts: nowS - 1, brain_alive: true,
    trading_allowed: true, trading_allowed_reason: null, focus: [], trader_live: ['SMPL'], working: [], updated_ts: nowS - 1,
    last_rewind: null,
  };
}

function audit(ts: number, action: string, outcome: string, inputs: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  return {
    timestamp: ts, level: 2, strategy: null, brain_session_id: null, action, inputs, reason: null, order_id: null,
    advise_spend: null, outcome, venue: 'paper', ...extra,
  };
}

export function botAudit() {
  return [
    audit(at(9, 3, 31), 'bot_trade', 'closed', { symbol: 'SMPL', setup_type: 'first_pullback', setup_id: 'SMPL-2026-09-30-0834', exit_reason: 'target', r: 2.0 }, { brain_session_id: 'nova-first-pullback', order_id: 7004 }),
    audit(at(8, 52, 3), 'bot_trade', 'filled', { symbol: 'SMPL', setup_type: 'first_pullback', setup_id: 'SMPL-2026-09-30-0834', qty: 10, price: 3.8 }, { brain_session_id: 'nova-first-pullback', order_id: 7003 }),
    audit(at(8, 51, 58), 'setup_proposal', 'proposed', { symbol: 'SMPL', kind: 'first_pullback', tape_now: 'go', grade: 'A' }),
    audit(at(7, 13, 2), 'setup_proposal', 'disarmed', { symbol: 'SMPL', kind: 'bull_flag' }, { reason: 'the flag gave back too much of the pole' }),
    audit(at(6, 58, 40), 'activate', 'ok', {}, { reason: 'desk' }),
    audit(at(6, 58, 31), 'level', '1->2', { from: 1, to: 2 }),
  ];
}

function leg(h: number, m: number, high: number, low: number, bars = 3) {
  return { t: at(h, m), high, low, pct: r2(((high - low) / low) * 10000) / 10000, bars };
}

interface BoardSetup {
  trigger: number;
  entry: number;
  stop: number;
  risk: number;
  target1: number;
  armed_at?: number;
  triggered_at?: number;
  detail?: unknown;
  [k: string]: unknown;
}

interface BoardRow {
  symbol: string;
  setup_type: string;
  state: string;
  reason: string;
  kind: string;
  setup_id: string | null;
  last_price: number | null;
  distance: number | null;
  grade: string | null;
  setup: BoardSetup | null;
  tape: { verdict: string; reasons: string[]; [k: string]: unknown } | null;
  trigger_tape: { verdict: string; reasons: string[] } | null;
  outcome: string | null;
  outcome_at: number | null;
  bar_r: number | null;
  mfe: number | null;
  mae: number | null;
  [k: string]: unknown;
}

type BoardRowInput = Partial<BoardRow> & Pick<BoardRow, 'symbol' | 'setup_type' | 'state' | 'reason' | 'kind'>;

function boardRow(o: BoardRowInput): BoardRow {
  return {
    nth: 0, setup_id: null, last_price: null, distance: null, grade: null, setup: null, leg: null, pillars: null, tape: null,
    proposal: null, outcome: null, bar_r: null, mfe: null, mae: null, failed_at: null, graded: null, phase: null,
    trigger_tape: null, outcome_at: null, liquidity: null, tf5: null, tf5_at: null, ...o,
  };
}

function pillars(price: number, chg: number, rvol: number, float: number, news: boolean, headline: string | null) {
  return { price, change_pct: chg, rvol, float, float_contradicted: false, shares_outstanding: null, float_note: null, news, headline, catalyst: null, volume: null };
}

const counts = (o: Record<string, number>) => ({ watching: 31, forming: 0, armed: 0, near: 0, triggered: 0, failed: 0, filtered: 0, proposed: 0, ...o });

function summary(id: string, level: number, window: { start: string; end: string }, c: Record<string, number>) {
  return {
    id, level, chosen: false, proposing: level >= 1, template: { id: 'default', rev: 1, name: 'Default (pre-registered)' },
    templates_watched: 1, window: { ...window, state: 'open' }, counts: counts(c),
  };
}

const MORNING = { start: '07:00', end: '11:30' };

const BOARD_ROWS = [
  boardRow({
    symbol: 'SMPL', setup_type: 'first_pullback', state: 'near', reason: '0.05 under the 4.38 trigger -- read the tape', kind: 'first_pullback',
    setup_id: 'SMPL-2026-09-30-0932', last_price: 4.33, distance: 0.05, grade: 'A', graded: 'armed',
    setup: { trigger: 4.38, entry: 4.39, stop: 4.12, risk: 0.27, target1: 4.93, pullback_bars: 4, leg_high: 4.38, leg_low: 4.06, leg_pct: 0.0788, kind: 'first_pullback', leg_t: at(9, 32), armed_bar_t: at(9, 37), armed_at: at(9, 37) },
    leg: leg(9, 32, 4.38, 4.06), pillars: pillars(4.33, 54.6, 24.8, 4_200_000, true, 'Sample Pharma receives FDA Fast Track designation'),
    tape: { verdict: 'go', reasons: ['buyers lifting the offer (2.4k at the ask in 10 s)', 'no seller stacked at the trigger'], line: { depth: true, tape: true }, metrics: {} },
    tf5: { agrees: true, above_ema9: true, macd_up: true, close: 4.31, ema9: 4.19, macd_hist: 0.031, candles: 69, as_of: at(9, 35) }, tf5_at: 'armed',
  }),
  boardRow({
    symbol: 'GAPX', setup_type: 'bull_flag', state: 'armed', reason: 'flag of 2 under the 1.94 pole: trigger 1.93', kind: 'bull_flag',
    setup_id: 'GAPX-2026-09-30-1@bull_flag', last_price: 1.92, distance: 0.01, grade: 'A', graded: 'armed',
    setup: { trigger: 1.93, entry: 1.94, stop: 1.87, risk: 0.07, target1: 2.08, pullback_bars: 2, leg_high: 1.94, leg_low: 1.78, leg_pct: 0.0899, kind: 'bull_flag', detail: { pole_bars: 3, flag_bars: 2 } },
    leg: leg(9, 35, 1.94, 1.78), pillars: pillars(1.92, 74.5, 42.3, 1_800_000, true, 'GapX Holdings signs merger agreement'),
    tape: { verdict: 'wait', reasons: ['quiet tape at the trigger'], line: { depth: true, tape: true }, metrics: {} },
  }),
  boardRow({
    symbol: 'HODX', setup_type: 'flat_top_breakout', state: 'armed', reason: 'three tops at 9.24: trigger 9.25', kind: 'flat_top_breakout',
    setup_id: 'HODX-2026-09-30-1@flat_top_breakout', last_price: 9.2, distance: 0.04, grade: 'B', graded: 'armed',
    setup: { trigger: 9.24, entry: 9.25, stop: 9.06, risk: 0.19, target1: 9.63, pullback_bars: 5, leg_high: 9.24, leg_low: 8.81, leg_pct: 0.0488, kind: 'flat_top_breakout' },
    leg: leg(9, 26, 9.24, 8.81, 5), pillars: pillars(9.2, 31.4, 14.3, 8_000_000, true, null),
    tape: { verdict: 'blind', reasons: ['no Level 2 line open for HODX'], line: { depth: false, tape: false }, metrics: {} },
  }),
  boardRow({
    symbol: 'RUNR', setup_type: 'first_pullback', state: 'triggered', reason: 'traded 6.18 over the 6.17 trigger', kind: 'first_pullback',
    setup_id: 'RUNR-2026-09-30-1', last_price: 6.8, grade: 'A', graded: 'armed',
    setup: { trigger: 6.17, entry: 6.18, stop: 6.02, risk: 0.16, target1: 6.5, pullback_bars: 2, leg_high: 6.21, leg_low: 5.71, leg_pct: 0.0876, kind: 'first_pullback', triggered_at: at(9, 20, 6) },
    leg: leg(9, 14, 6.21, 5.71), pillars: pillars(6.8, 65.9, 31.2, 3_300_000, true, null),
    trigger_tape: { verdict: 'go', reasons: ['buyers lifting the offer'] }, outcome: 'target_first', outcome_at: at(9, 26, 40), bar_r: 2.0, mfe: 0.62, mae: -0.04,
  }),
  boardRow({
    symbol: 'FLTX', setup_type: 'first_pullback', state: 'leg', reason: 'new high 0.89 on a 9.9% leg -- wait for the pullback', kind: 'first_pullback',
    last_price: 0.88, leg: leg(9, 40, 0.89, 0.81), graded: 'forming', grade: 'B',
  }),
  boardRow({
    symbol: 'MMTX', setup_type: 'red_to_green', state: 'leg', reason: '1 close under the 2.98 open', kind: 'red_to_green',
    last_price: 3.15, leg: leg(9, 31, 2.98, 2.91, 1),
  }),
];

export function setupsBoard(nowS: number) {
  return {
    type: 'board', schema_version: 2, source: 'live', generated_at: nowS - 1, session_date: DAY,
    universe: 31, universe_symbols: ['BZAP', 'CATZ', 'FLTX', 'GAPX', 'HELQ', 'HODX', 'KRYQ', 'MMTX', 'NWSR', 'ORBQ', 'RDYN', 'RUNR', 'SMPL', 'SPIK', 'VLTG', 'VYTL'],
    seeding: 0, scoreboard: true, scoreboard_error: null, proposing: true, template: null, templates_watched: 1, replay: null,
    setups: [
      summary('first_pullback', 2, MORNING, { armed: 2, near: 1, triggered: 2, forming: 1, proposed: 2 }),
      summary('bull_flag', 1, MORNING, { armed: 1, forming: 1, failed: 1 }),
      summary('flat_top_breakout', 1, MORNING, { armed: 1 }),
      summary('red_to_green', 0, { start: '09:30', end: '10:30' }, { forming: 1 }),
    ],
    proposals: [],
    rows: BOARD_ROWS,
  };
}

export function setupRows() {
  return BOARD_ROWS.flatMap((r, i) => {
    const setup = r.setup;
    if (!setup) return [];
    return [{
      id: r.setup_id, date: DAY, symbol: r.symbol, setup_type: r.setup_type, kind: r.kind, template_id: 'default', template_rev: 1,
      params_hash: 'sample', armed_at: setup.armed_at ?? at(9, 20 + i), trigger: setup.trigger, entry: setup.entry, stop: setup.stop,
      risk: setup.risk, target1: setup.target1, grade: r.grade, pillars: r.pillars, near_tape: r.tape ? r.tape.verdict : null,
      trigger_tape: r.trigger_tape ? r.trigger_tape.verdict : null, triggered_at: setup.triggered_at ?? null,
      outcome: r.outcome, outcome_at: r.outcome_at, bar_r: r.bar_r, mfe: r.mfe, mae: r.mae, detail: setup.detail ?? null, liquidity: null,
    }];
  });
}

export function stockModes(venue: string) {
  const view = (symbol: string, mode: string, buy: string, sell: string, last: { ts: number; tone: string; text: string } | null) => ({
    schema_version: 1, symbol, generated_at: NOW_S, venue, mode, buy, sell, risk_usd: 50, set_at: at(6, 59),
    locks: { buy: null, sell: null }, notes: [], approval: null, trade: null, entries_today: { count: 1, cap: 3 }, nova_entries_today: 1,
    size: { qty: 10, by_risk: 185, capped_by: 'max_shares', text: '10 shares (max shares)' }, last_event: last,
    bot: { on_list: mode === 'bot', playing: mode === 'bot', reason: null, setup_at_strategy: true, active: true },
  });
  return {
    schema_version: 1, generated_at: NOW_S, venue,
    stocks: [
      view('SMPL', 'bot', 'nova', 'nova', { ts: at(9, 3, 31), tone: 'ok', text: 'Sold 10 at 4.02 · target · +2.0R' }),
      view('RUNR', 'bot', 'nova', 'nova', null),
      view('GAPX', 'signal', 'you', 'nova', { ts: at(9, 37, 20), tone: 'info', text: 'Nova holds the exit: stop 1.82' }),
    ],
  };
}
