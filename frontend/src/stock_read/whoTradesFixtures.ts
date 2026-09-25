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
    reason: '',
    tape: { verdict: 'go', reasons: ['green on the tape'] },
    flow: null,
    window: { start: '07:00', end: '11:30', state: 'open' },
    checks: [],
    marks: [],
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
    no_scanner: [],
    plan: pfsaPlan(state, planOver),
    levels: { hod: { price: 4.6, ts: pfsaAt(8, 4) }, pmh: 4.6, open: null, prev_close: 2.05, vwap: 3.9,
      round_above: 4.5, round_below: 4.0 },
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

export function pfsaView(mode: StockModeName, over: Partial<StockModeView> = {}): StockModeView {
  const [buy, sell] = SIDES[mode];
  return {
    symbol: 'PFSA',
    generated_at: PFSA_TRIGGER,
    venue: 'paper',
    mode,
    buy,
    sell,
    risk_usd: mode === 'auto_entry' ? 20 : null,
    set_at: null,
    locks: { buy: null, sell: null },
    notes: [],
    approval: null,
    trade: null,
    nova_entries_today: 0,
    last_event: null,
    bot: mode === 'bot' ? { on_list: true, playing: true, reason: 'playing', setup: 'first_pullback' } : null,
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

export function inputs(over: Partial<MomentInputs> = {}, held: HeldMemory = NO_HELD): MomentInputs {
  return {
    read: pfsaRead('triggered'),
    who: pfsaView('signal'),
    position: null,
    last: 4.26,
    now: PFSA_TRIGGER + 2,
    riskUsd: 20,
    held,
    ...over,
  };
}
