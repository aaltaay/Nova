/**
 * PFSA's first pullback on 2026-09-24 as the approved v2 mockup drew it (ADR 037): the trigger printed
 * 4.26 at 08:07:02 ET with the tape at go; entry 4.27, stop 4.14, target 4.52 (2R on a 0.13 risk).
 * Typed shapes for the Who trades tests; the desk never reads this.
 */
import { NO_HELD, type HeldMemory, type MomentInputs } from './momentModel';
import type {
  SetupLane,
  StockModeName,
  StockModeTrade,
  StockModeView,
  StockPlan,
  StockRead,
} from './types';

/** Epoch seconds of an Eastern wall-clock time that day (EDT, UTC-4). */
export function pfsaAt(h: number, m: number, s = 0): number {
  return Date.UTC(2026, 8, 24, h + 4, m, s) / 1000;
}

export const PFSA_TRIGGER = pfsaAt(8, 7, 2);
export const PFSA_SETUP_ID = 'PFSA-2026-09-24-1790239560';

export function pfsaPlan(state: StockPlan['state'], over: Partial<StockPlan> = {}): StockPlan {
  return {
    source: 'setup',
    setup_type: 'first_pullback',
    setup_id: state === 'forming' ? null : PFSA_SETUP_ID,
    kind: 'first_pullback',
    state,
    provisional: state === 'forming',
    trigger: 4.26,
    entry: 4.27,
    stop: 4.14,
    target: 4.52,
    risk: 0.13,
    reward: 0.25,
    rr: 2,
    target_rule: 'entry + 2 x risk',
    entry_rule: '1 cent over the trigger',
    stop_rule: 'the pullback low',
    grade: 'B',
    pillars: { passed: 4, known: 5, total: 5 },
    trade: { ok: true, reasons: [] },
    result: null,
    reason: '',
    tape: { verdict: 'go', reasons: ['green on the tape'] },
    flow: null,
    window: { start: '07:00', end: '11:30', state: 'open' },
    checks: [],
    marks: [],
    levels: null,
    ...over,
  };
}

function lane(state: string, distance: number | null): SetupLane {
  return {
    setup_type: 'first_pullback',
    state,
    reason: '',
    kind: 'first_pullback',
    chosen: true,
    level: 1,
    setup: state === 'forming' ? null : {
      trigger: 4.26, entry: 4.27, stop: 4.14, risk: 0.13, target1: 4.52,
      triggered_at: state === 'triggered' ? PFSA_TRIGGER : undefined,
      trigger_price: state === 'triggered' ? 4.26 : undefined,
    },
    forming: null,
    leg: { t: pfsaAt(8, 4), high: 4.6, low: 3.66, pct: 0.258 },
    last_price: 4.26,
    distance,
    grade: 'B',
    phase: null,
    tape: { verdict: 'go', reasons: [] },
    window: { start: '07:00', end: '11:30', state: 'open' },
    series: null,
  };
}

export function pfsaRead(state: StockPlan['state'], planOver: Partial<StockPlan> = {}, distance: number | null = 0.03): StockRead {
  return {
    schema_version: 1,
    symbol: 'PFSA',
    generated_at: PFSA_TRIGGER,
    session_date: '2026-09-24',
    price: 4.26,
    prev_close: 2.05,
    change_pct: 1.078,
    followed: true,
    followed_note: null,
    setups: [lane(state === 'manual' ? 'watching' : state, distance)],
    setups_5m: [],
    no_scanner: [],
    plan: pfsaPlan(state, planOver),
    levels: { hod: { price: 4.6, ts: pfsaAt(8, 4) }, pmh: 4.6, open: null, prev_close: 2.05, vwap: 3.9,
      round_above: 4.5, round_below: 4.0 },
    level_map: null,
    groups: [],
    counts: { ok: 0, warn: 0, bad: 0, unknown: 0, info: 0 },
  };
}

const SIDES: Record<StockModeName, [StockModeView['buy'], StockModeView['sell']]> = {
  signal: ['you', 'you'],
  approve: ['you', 'nova'],
  auto_entry: ['nova', 'you'],
  bot: ['nova', 'nova'],
};

/** The bot as the view says it when nothing stands in its way: the plan's setup at Strategy, active, playing. */
export const BOT_READY: NonNullable<StockModeView['bot']> = {
  on_list: true, playing: true, reason: 'playing', setup_at_strategy: true, active: true, setup: null,
};

export function pfsaView(mode: StockModeName, over: Partial<StockModeView> = {}): StockModeView {
  const [buy, sell] = SIDES[mode];
  const nova = mode !== 'signal';
  return {
    symbol: 'PFSA',
    generated_at: PFSA_TRIGGER,
    venue: 'paper',
    mode,
    buy,
    sell,
    risk_usd: 20,
    set_at: null,
    locks: { buy: null, sell: null },
    notes: [],
    approval: null,
    trade: null,
    // The Paper sleeve: $20 over the 0.13 risk is 153 shares, under its max shares of 200.
    size: nova ? { qty: 153, by_risk: 153, capped_by: null, text: '$20 risk over 0.13 a share' } : null,
    entries_today: { count: 0, cap: 1 },
    nova_entries_today: 0,
    last_event: null,
    bot: mode === 'bot' ? BOT_READY : null,
    ...over,
  };
}

export function pfsaTrade(kind: StockModeTrade['kind'], state: StockModeTrade['state'],
  over: Partial<StockModeTrade> = {}): StockModeTrade {
  const filled = state === 'holding' || state === 'closed';
  return {
    kind,
    state,
    venue: 'paper',
    venue_day: '2026-09-24',
    setup_id: PFSA_SETUP_ID,
    setup_type: 'first_pullback',
    qty: 153,
    entry: 4.27,
    stop: 4.14,
    target: 4.52,
    entry_order_id: 101,
    target_order_id: kind === 'auto_entry' ? null : 102,
    stop_order_id: kind === 'approve' ? 103 : null,
    fill_price: filled ? 4.27 : null,
    filled_at: filled ? PFSA_TRIGGER + 0.5 : null,
    exit_price: null,
    exit_reason: null,
    exits: kind === 'auto_entry' ? 'you' : 'nova',
    sent_at: PFSA_TRIGGER + 0.2,
    closed_at: null,
    note: null,
    exiting: false,
    ...over,
  };
}

/** `GET /api/bot/session` as far as the sleeve's risk per trade reads it (ADR 042 draft): the desk venue's
 * `caps`, every venue's, and the bounds. */
export function sleeveSessionWire(riskUsd: number | null = 20, venue: 'live' | 'paper' | 'sim' = 'paper'): Record<string, unknown> {
  const caps = (v: string, risk: number | null) => ({
    venue: v, ...(risk === null ? {} : { risk_usd: risk }), max_shares: 10, bp_budget_usd: 50, working_ttl_sec: 3,
    extended_hours: false, entries_per_day: 1, api_kinds: [], allowlist: [],
  });
  return {
    level: 2,
    active: false,
    caps: caps(venue, riskUsd),
    caps_bounds: { risk_usd: [1, 10_000], max_shares: [1, 10], bp_budget_usd: [0.01, 50], working_ttl_sec: [1, 10],
      entries_per_day: [1, 3] },
    caps_by_venue: { live: caps('live', riskUsd === null ? null : 20), paper: caps('paper', riskUsd),
      sim: caps('sim', riskUsd === null ? null : 20), [venue]: caps(venue, riskUsd) },
  };
}

export function inputs(over: Partial<MomentInputs> = {}, held: HeldMemory = NO_HELD): MomentInputs {
  return {
    read: pfsaRead('triggered'),
    who: pfsaView('signal'),
    position: null,
    last: 4.26,
    now: PFSA_TRIGGER + 2,
    riskUsd: 20,
    ttlSec: 10,
    held,
    ...over,
  } as MomentInputs;
}
