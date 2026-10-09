/**
 * SMPL's "bot's read" at 09:41:27 ET in the ADR 036 wire shapes (ADR 043): Nova Marketing Sample
 * Data. The wording stays generic on purpose -- no strategy parameters from a private playbook.
 */
import { DAY, NOW_S, etMs, type Bar } from './market';
import type { ScannerRow } from './universe';

const at = (h: number, m: number, s = 0) => etMs(h, m, s) / 1000;
type State = 'ok' | 'warn' | 'bad' | 'unknown' | 'info';
const row = (id: string, label: string, value: string, state: State, source: string) => (
  { id, label, value, state, source, detail: null, as_of: NOW_S - 2 }
);

const series = { bars_as_of: at(9, 40), close: 4.31, ema: 4.26, macd_line: 0.021, macd_signal: 0.012, macd_hist: 0.009, hod: 4.38 };
const SETUP = {
  trigger: 4.38, entry: 4.39, stop: 4.12, risk: 0.27, target1: 4.93,
  leg_t: at(9, 32), leg_high: 4.38, leg_low: 4.06, pullback_bars: 4, armed_bar_t: at(9, 37),
};
const LEG = { t: at(9, 32), high: 4.38, low: 4.06, pct: 0.0788, bars: 3 };
const LIQUIDITY = {
  state: 'ok', reasons: [], failed: [], unknown: {}, day_dollars: 118_400_000, pace_dollars: 5_600_000, pace_sec: 300,
  walk: { qty: 185, best_ask: 4.33, last: 4.33, avg: 4.33, over_ask: 0, shown: 1900, short: 0, r: 0 },
  as_of: NOW_S - 2, limits: { day_dollars: 2_000_000, pace_dollars: 100_000, walk_r: 0.25 },
};

function lane(setup_type: string, state: string, reason: string, extra: Record<string, unknown> = {}) {
  return {
    setup_type, state, reason, kind: null, chosen: false, level: 1, setup: null, forming: null, leg: null,
    last_price: 4.33, distance: null, grade: null, phase: null, tape: null, window: null, series, timeframe: '1m', ...extra,
  };
}

interface Member {
  kind: string;
  price: number;
  label: string;
  touches?: number;
  times?: number[];
  dates?: string[];
  note?: string;
}

const member = (m: Member) => ({ touches: null, times: [], dates: [], note: null, ...m });

function zone(id: string, home: string, lo: number, hi: number, side: 'above' | 'below', strength: number, label: string, tag: string, members: Member[]) {
  return { id: `${home}:${id}`, lo, hi, price: side === 'above' ? lo : hi, side, strength, label, tag, home, members: members.map(member) };
}

const LEVEL_MAP = {
  schema_version: 1,
  price: 4.33,
  rounds: { minor: 0.5, major: 1, measured: true, words: 'half and whole dollars' },
  intraday: [
    zone('4.50', 'intraday', 4.5, 4.5, 'above', 2, '$4.50 · half dollar', '$4.50', [{ kind: 'half', price: 4.5, label: '$4.50', note: 'half dollar' }]),
    zone('4.38', 'intraday', 4.37, 4.38, 'above', 4, '4.38 · HOD · double top', '4.38', [
      { kind: 'hod', price: 4.38, label: 'HOD', times: [at(9, 32)] },
      { kind: 'top', price: 4.37, label: 'double top', touches: 2, times: [at(9, 32), at(9, 39)] },
    ]),
    zone('4.12', 'intraday', 4.12, 4.13, 'below', 3, '4.12 · PMH · bottom', '4.12', [
      { kind: 'pmh', price: 4.12, label: 'PMH' },
      { kind: 'bottom', price: 4.13, label: 'bottom', touches: 2, times: [at(9, 36), at(9, 26)] },
    ]),
    zone('4.00', 'intraday', 4.0, 4.01, 'below', 2, '$4.00 · whole dollar', '$4.00', [{ kind: 'whole', price: 4.0, label: '$4.00', note: 'whole dollar' }]),
  ],
  five_minute: [
    zone('4.50', 'five_minute', 4.5, 4.5, 'above', 2, '$4.50 · half dollar', '$4.50', [{ kind: 'half', price: 4.5, label: '$4.50', note: 'half dollar' }]),
    zone('4.38', 'five_minute', 4.38, 4.38, 'above', 3, '4.38 · HOD', '4.38', [{ kind: 'hod', price: 4.38, label: 'HOD', times: [at(9, 30)] }]),
    zone('4.12', 'five_minute', 4.12, 4.12, 'below', 3, '4.12 · PMH', '4.12', [{ kind: 'pmh', price: 4.12, label: 'PMH' }]),
    zone('3.84', 'five_minute', 3.84, 3.86, 'below', 2, '3.84 · top ×2', '3.84', [{ kind: 'top', price: 3.84, label: 'top', touches: 2, times: [at(7, 5), at(8, 30)] }]),
    zone('3.60', 'five_minute', 3.58, 3.6, 'below', 2, '3.58 · bottom ×3', '3.58', [{ kind: 'bottom', price: 3.58, label: 'bottom', touches: 3, times: [at(7, 10), at(7, 35), at(8, 5)] }]),
  ],
  daily: [
    zone('5.24', 'daily', 5.18, 5.24, 'above', 3, '5.24 · daily highs ×2', '5.24', [{ kind: 'daily_highs', price: 5.24, label: 'daily highs', touches: 2, dates: ['2026-06-12', '2026-07-21'] }]),
    zone('4.62', 'daily', 4.58, 4.62, 'above', 2, '4.62 · 200-day', '4.62', [{ kind: 'sma200', price: 4.62, label: '200-day' }]),
    zone('2.88', 'daily', 2.88, 2.88, 'below', 2, '2.88 · yesterday high', '2.88', [{ kind: 'yday_high', price: 2.88, label: 'yesterday high' }]),
  ],
  daily_sessions: 262,
  daily_error: null,
  study: { source: 'sample', round_turn: [24, 16], round_through: [76, 84], round_lost: [68, 63], hod_past: [61, 57], top_past: [59, 56], daily_past: [51, 50] },
};

const PLAN = {
  source: 'setup', setup_type: 'first_pullback', setup_id: 'SMPL-2026-09-30-0932', kind: 'first_pullback', state: 'near',
  provisional: false, trigger: 4.38, entry: 4.39, stop: 4.12, target: 4.93, risk: 0.27, reward: 0.54, rr: 2.0,
  target_rule: 'entry + 2 x risk', entry_rule: 'the break of the leg high', stop_rule: "under the pullback's low",
  grade: 'A', pillars: { passed: 5, known: 5, total: 5 }, trade: { ok: true, reasons: [] }, result: null,
  reason: 'pulled back four candles, holding over VWAP; 0.05 under the trigger',
  tape: { verdict: 'go', reasons: ['buyers lifting the offer', 'no seller stacked at the trigger'] },
  flow: { score: 0.62, label: 'burst' }, window: null,
  checks: [
    { id: 'liquidity', state: 'ok', text: '$118M traded today · $5.6M in 5 min' },
    { id: 'macd', state: 'ok', text: '1-min MACD rising (+0.009)' },
    { id: 'ema9', state: 'ok', text: 'above the 9 EMA 4.26' },
    { id: 'vwap', state: 'ok', text: 'above VWAP 3.79' },
    { id: 'spread', state: 'ok', text: 'spread 0.01 · tight' },
    { id: 'in_way_round', state: 'warn', text: '$4.50 before the target' },
    { id: 'tf5', state: 'info', text: '5m agrees: over its 9 EMA, MACD up' },
  ],
  marks: [{ price: 4.5, label: '$4.50', kind: 'round', size: null }],
  levels: {
    room: { state: 'warn', text: 'Room 0.4R to $4.50', detail: 'The first level over the entry is the half dollar.', r: 0.41, price: 4.5, trial: 'T7' },
    target: { state: 'ok', text: 'Target 4.93 sells before $5.00', detail: null },
    stop: { state: 'ok', text: 'Stop under the 4.12 premarket high', detail: null },
    next: { state: 'info', text: '$4.50 next: resistance until it prints through', detail: null },
    recent: { state: 'ok', text: 'Broke $4.00 at 09:18', detail: null },
    between: [{ price: 4.5, lo: 4.5, hi: 4.5, tag: '$4.50', label: '$4.50 · half dollar', round: true, hod: false }],
  },
  liquidity: LIQUIDITY,
};

const GROUPS = [
  { id: 'in_play', label: 'In play', question: 'Is this a stock people are trading right now?', verdict: 'ok', value: 'Yes', rows: [
    row('hod_today', 'HOD Momo today', '12 alerts since 07:01', 'ok', 'HOD Momo alert history'),
    row('catalyst', 'Catalyst', 'FDA / regulatory · strong', 'ok', 'Catalyst verdict'),
    row('rvol', 'Relative volume', '24.8x', 'ok', 'RVOL sensor'),
    row('liquidity', 'Liquidity', '$118M today', 'ok', 'Volume x price'),
    row('ran_before', 'Has it run before?', '3 runs of +40% in a year', 'warn', 'Daily bars'),
  ] },
  { id: 'setups', label: 'Setups', question: 'Is a playbook setup forming, and what is it waiting for?', verdict: 'ok', value: 'Near trigger', rows: [
    row('lane_first_pullback', 'First pullback', 'Near · 0.05 under 4.38', 'ok', "The setup scanner's lanes"),
    row('lane_bull_flag', 'Bull flag', 'Watching · no pole yet', 'info', "The setup scanner's lanes"),
  ] },
  { id: 'front', label: 'Front side', question: 'Is momentum still up, or is it fading?', verdict: 'ok', value: 'Strong', rows: [
    row('macd_1m', 'MACD 1-minute', 'hist +0.009 · rising', 'ok', 'The 1-minute bars'),
    row('vwap', 'VWAP', '0.54 over 3.79 (+14.2%)', 'ok', 'Session VWAP from 04:00'),
    row('hod', 'High of day', '4.38 at 09:32', 'ok', 'HOD Momo high'),
  ] },
  { id: 'tape', label: 'Tape', question: 'What are Level 2 and the tape doing right now?', verdict: 'ok', value: 'Buyers', rows: [
    row('spread', 'Spread', '0.01 · 4.32 x 4.33 (0.2%)', 'ok', 'Level 2'),
    row('flow', 'Flow', 'Burst +0.62', 'ok', 'Tape flow score'),
    row('pulls', 'Pulled bids', 'None in 60 s', 'ok', 'Book watcher'),
    row('hidden', 'Hidden size', 'None', 'info', 'Book watcher'),
  ] },
  { id: 'short', label: 'Short', question: 'Can shorts press it? Tight borrow means fewer sellers.', verdict: 'ok', value: 'Hard to borrow', rows: [
    row('borrow', 'Borrow (IBKR)', '18% fee · 30K left', 'ok', 'IBKR short-stock file'),
    row('short_interest', 'Short interest', '610K (Sep 15)', 'info', 'FINRA via Yahoo'),
  ] },
  { id: 'float', label: 'Float', question: 'How many shares can trade?', verdict: 'ok', value: '4.2M', rows: [
    row('float', 'Float', '4.2M shares', 'ok', 'Yahoo fundamentals'),
    row('rotation', 'Float rotation', '7.4x today', 'ok', 'Volume / float'),
  ] },
  { id: 'halts', label: 'Halts', question: 'What could stop me out or freeze me?', verdict: 'ok', value: 'No halts', rows: [
    row('halted', 'Halted now', 'No', 'ok', 'IBKR + Nasdaq halts'),
    row('halts_today', 'Halts today', 'None', 'ok', 'Halt log'),
  ] },
];

const fmtM = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : `${Math.round(n / 1e3)}K`);

/** The quieter read of any other sample symbol: its own numbers, no setup forming. */
function groupsFor(r: ScannerRow) {
  const dollars = r.price * r.volume;
  const news = r.catalyst ? `${r.catalyst.category.replace(/_/g, ' ')} · ${r.catalyst.strength}` : 'No news found';
  return [
    { id: 'in_play', label: 'In play', question: 'Is this a stock people are trading right now?', verdict: 'ok', value: 'Yes', rows: [
      row('catalyst', 'Catalyst', news, r.catalyst?.verdict === 'catalyst' ? 'ok' : 'info', 'Catalyst verdict'),
      row('rvol', 'Relative volume', `${r.rel_volume.toFixed(1)}x`, r.rel_volume >= 5 ? 'ok' : 'warn', 'RVOL sensor'),
      row('liquidity', 'Liquidity', `$${fmtM(dollars)} today`, dollars >= 2e6 ? 'ok' : 'warn', 'Volume x price'),
    ] },
    { id: 'setups', label: 'Setups', question: 'Is a playbook setup forming, and what is it waiting for?', verdict: 'info', value: 'Watching', rows: [
      row('lane_first_pullback', 'First pullback', 'Watching · no leg yet', 'info', "The setup scanner's lanes"),
    ] },
    { id: 'float', label: 'Float', question: 'How many shares can trade?', verdict: r.float <= 10e6 ? 'ok' : 'warn', value: fmtM(r.float), rows: [
      row('float', 'Float', `${fmtM(r.float)} shares`, r.float <= 10e6 ? 'ok' : 'warn', 'Yahoo fundamentals'),
      row('rotation', 'Float rotation', `${(r.volume / r.float).toFixed(1)}x today`, 'info', 'Volume / float'),
    ] },
    { id: 'halts', label: 'Halts', question: 'What could stop me out or freeze me?', verdict: 'ok', value: 'No halts', rows: [
      row('halted', 'Halted now', 'No', 'ok', 'IBKR + Nasdaq halts'),
    ] },
  ];
}

/** The stock read: SMPL's own, and a quieter one (no setup forming) for every other sample symbol. */
export function stockRead(r: ScannerRow, nowS: number) {
  const smpl = r.symbol === 'SMPL';
  const groups = smpl ? GROUPS : groupsFor(r);
  const counts: Record<State, number> = { ok: 0, warn: 0, bad: 0, unknown: 0, info: 0 };
  for (const g of groups) for (const x of g.rows) counts[x.state] += 1;
  return {
    schema_version: 1, symbol: r.symbol, generated_at: nowS - 1, session_date: DAY,
    price: r.price, prev_close: r.prev_close, change_pct: (r.price - r.prev_close) / r.prev_close,
    followed: true, followed_note: null, replay: false,
    setups: smpl
      ? [
        lane('first_pullback', 'near', 'pulled back four candles; 0.05 under the trigger', {
          kind: 'first_pullback', chosen: true, level: 2, setup: SETUP, leg: LEG, distance: 0.05, grade: 'A',
          tape: { verdict: 'go', reasons: ['buyers lifting the offer'] }, liquidity: LIQUIDITY,
        }),
        lane('bull_flag', 'watching', 'no pole yet'),
        lane('flat_top_breakout', 'watching', 'no base yet', { level: 0 }),
        lane('red_to_green', 'watching', 'opened green', { level: 0 }),
      ]
      : [lane('first_pullback', 'watching', 'no leg yet', { last_price: r.price })],
    setups_5m: [],
    no_scanner: [],
    plan: smpl ? PLAN : null,
    held: null,
    levels: smpl
      ? { hod: { price: 4.38, ts: at(9, 32) }, pmh: 4.12, open: 4.18, prev_close: 2.8, vwap: 3.79, round_above: 4.5, round_below: 4.0 }
      : { hod: null, pmh: null, open: r.open, prev_close: r.prev_close, vwap: null, round_above: null, round_below: null },
    level_map: smpl ? LEVEL_MAP : { ...LEVEL_MAP, price: r.price, rounds: null, intraday: [], five_minute: [], daily: [], daily_sessions: 0 },
    groups,
    counts,
  };
}

export function pastSetups(symbol: string, tf: string | null) {
  const base = { schema_version: 1, symbol, date: DAY, generated_at: NOW_S, journal: { ok: true, error: null, lines: 812 }, bars: { ok: true, error: null, count: 342 } };
  if (tf === '5m' || symbol !== 'SMPL') return { ...base, timeframe: tf === '5m' ? '5m' : '1m', episodes: [], counts: {} };
  return {
    ...base,
    timeframe: '1m',
    episodes: [
      {
        id: 'ep-1', symbol, setup_type: 'bull_flag', template: 'default', rev: 1,
        started_at: at(7, 6), ended_at: at(7, 14), end: 'failed', died_at: at(7, 13), died_bar_t: at(7, 12),
        reason: 'the flag gave back too much of the pole', reason_key: 'flag too deep', ended_by: null, reached: 'pullback',
        leg: { t: at(7, 8), high: 3.84, low: 3.4, pct: 0.129, bars: 3 }, setup: null, setup_id: null, filtered: null,
        triggered_at: null, trigger_price: null, score: null,
        after: { from_ts: at(7, 13), price: 3.6, level: 3.84, entry: 3.85, floor: 3.55, window_min: 15, complete: true, bars: 15, high: 3.7, low: 3.56, first: 'neither', crossed_at: null, trade: null },
      },
      {
        id: 'ep-2', symbol, setup_type: 'first_pullback', template: 'default', rev: 1,
        started_at: at(8, 21), ended_at: at(8, 40), end: 'triggered', died_at: null, died_bar_t: null,
        reason: null, reason_key: null, ended_by: null, reached: 'triggered',
        leg: { t: at(8, 34), high: 3.86, low: 3.66, pct: 0.055, bars: 4 },
        setup: { trigger: 3.79, entry: 3.8, stop: 3.69, risk: 0.11, target1: 4.02, leg_t: at(8, 34), armed_bar_t: at(8, 38) },
        setup_id: 'SMPL-2026-09-30-0834', filtered: null, triggered_at: at(8, 52), trigger_price: 3.8,
        score: { outcome: 'target_first', bar_r: 2.0, exit_reason: 'target' }, after: null,
      },
    ],
    counts: { failed: 1, faded: 0, triggered: 1, cut: 0, open: 0 },
  };
}

export function decisions(symbol: string) {
  const smpl = symbol === 'SMPL';
  return {
    schema_version: 1, symbol, date: DAY, generated_at: NOW_S,
    summary: smpl
      ? { text: 'The scanners saw 4 legs, armed 2 setups and triggered 1. The 08:52 trigger reached its 2R target first.', legs: 4, armed: 2, near: 2, triggered: 1, trades: 0, refusals: [] }
      : { text: `Nothing armed on ${symbol} today.`, legs: 0, armed: 0, near: 0, triggered: 0, trades: 0, refusals: [] },
    events: smpl ? [
      { ts: at(7, 1, 4), lane: 'market', event: 'catalyst', title: 'FDA Fast Track headline (GlobeNewswire)', detail: 'Catalyst · strong', count: 1, last_ts: null, levels: null },
      { ts: at(7, 1, 9), lane: 'hod_momo', event: 'alert', title: 'HOD Momo: 5min Surge at 3.21', detail: '12 alerts today', count: 1, last_ts: null, levels: null },
      { ts: at(7, 13), lane: 'bull_flag', event: 'failed', title: 'Bull flag failed: the flag gave back too much of the pole', detail: null, count: 1, last_ts: null, levels: null },
      { ts: at(8, 38), lane: 'first_pullback', event: 'armed', title: 'First pullback armed: 3.80 / 3.69 / 4.02', detail: 'Grade A', count: 1, last_ts: null, levels: null },
      { ts: at(8, 52), lane: 'first_pullback', event: 'triggered', title: 'Triggered at 3.80 · tape GO', detail: 'Target first · +2.0R', count: 1, last_ts: null, levels: null },
      { ts: at(9, 32), lane: 'first_pullback', event: 'leg', title: 'New high 4.38 on a 7.9% leg', detail: null, count: 1, last_ts: null, levels: { leg: LEG, setup: null } },
      { ts: at(9, 37), lane: 'first_pullback', event: 'armed', title: 'First pullback armed: 4.39 / 4.12 / 4.93', detail: 'Grade A', count: 1, last_ts: null, levels: { leg: LEG, setup: SETUP } },
      { ts: at(9, 41, 2), lane: 'first_pullback', event: 'near', title: 'Near the trigger · tape GO', detail: 'buyers lifting the offer', count: 1, last_ts: null, levels: null },
    ] : [],
    sources: { journal: { ok: true, error: null }, hod_momo: { ok: true, error: null }, borrow: { ok: true, error: null }, catalysts: { ok: true, error: null }, bot: { ok: true, error: null } },
  };
}

export function history(symbol: string, daily: Bar[]) {
  const today = daily[daily.length - 1];
  return {
    schema_version: 1, symbol, generated_at: NOW_S,
    daily: daily.map((b) => ({ d: new Date(b.t).toISOString().slice(0, 10), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v })),
    runs: [
      { date: DAY, prior_close: 2.8, high: today.h, close: today.c, run_pct: (today.h - 2.8) / 2.8, close_pct: (today.c - 2.8) / 2.8, today: true },
      { date: '2026-07-21', prior_close: 4.41, high: 6.71, close: 5.33, run_pct: 0.5215, close_pct: 0.2086, today: false },
      { date: '2026-04-08', prior_close: 5.62, high: 8.51, close: 6.74, run_pct: 0.5142, close_pct: 0.1993, today: false },
      { date: '2025-12-23', prior_close: 7.88, high: 11.34, close: 9.12, run_pct: 0.4391, close_pct: 0.1574, today: false },
    ],
    split: null,
    holdings: [
      { id: 'setups', label: 'Setups armed', value: '2 today', state: 'info', source: 'The setups scoreboard', detail: null, as_of: null },
      { id: 'l2', label: 'Level 2 recorded', value: 'Today from 07:01', state: 'info', source: 'Session Record', detail: null, as_of: null },
    ],
  };
}

export function stockMode(symbol: string, mode = 'signal') {
  return {
    schema_version: 1, symbol, generated_at: NOW_S, venue: 'paper', mode, buy: mode === 'signal' ? 'you' : 'nova',
    sell: mode === 'bot' ? 'nova' : 'you', risk_usd: 50, set_at: null, locks: { buy: null, sell: null }, notes: [],
    approval: null, trade: null, entries_today: { count: 0, cap: 1 }, nova_entries_today: 0,
    size: { qty: 185, by_risk: 185, capped_by: null, text: '185 shares at $50 risk' }, last_event: null, bot: null,
  };
}

/** The book watcher's word on SMPL's ladder: a traded drop and a pulled one. */
export function bookWatch(nowS: number) {
  return {
    type: 'book_watch', symbol: 'SMPL',
    data: {
      schema_version: 1, now: nowS, reset: true, seq: 42, watching: true, reason: null, window_sec: 60,
      sides: {
        bid: { pulled_shares: 600, filled_shares: 9_800, large_pulls: 0, hidden_shares: 0 },
        ask: { pulled_shares: 2_400, filled_shares: 18_600, large_pulls: 1, hidden_shares: 0 },
      },
      drops: [
        { seq: 41, ts: nowS - 1.2, side: 'ask', price: 4.33, pulled: 0, filled: 3_500, outcome: 'traded', level_before: 5_400, level_after: 1_900, median_level: 900, distance_ticks: 0, distance_at_post_ticks: 1, lifetime_sec: 14.2, approached: true, large_pull: false, on_approach: false },
        { seq: 40, ts: nowS - 2.4, side: 'ask', price: 4.36, pulled: 2_400, filled: 0, outcome: 'pulled', level_before: 3_000, level_after: 600, median_level: 900, distance_ticks: 3, distance_at_post_ticks: 5, lifetime_sec: 6.1, approached: true, large_pull: true, on_approach: true },
      ],
      hidden: [],
      note: 'A hint consistent with spoofing, never a detection.',
    },
  };
}
