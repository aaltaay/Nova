/**
 * APUS at 15:03 ET on 2026-09-24 as the stock read answered it (the approved mockup's moment): the
 * bull flag's pole was up and one flag candle had closed, so the plan is provisional. Wire shapes,
 * for the tests and the visual check; the desk never reads this.
 */

/** Epoch seconds of an Eastern wall-clock minute that day (EDT, UTC-4). */
export function apusAt(h: number, m: number, s = 0): number {
  return Date.UTC(2026, 8, 24, h + 4, m, s) / 1000;
}

export const APUS_NOW = apusAt(15, 3, 5);

const series = {
  bars_as_of: apusAt(15, 2), bars: 600, close: 5.36, ema: 5.29, macd_line: -0.015, macd_signal: -0.033,
  macd_hist: 0.018, hod: 8.74,
};
const botWindow = { start: '07:00', end: '11:30', state: 'after' };

function row(id: string, label: string, value: string, state: string, source: string, detail: string | null = null) {
  return { id, label, value, state, source, detail, as_of: null };
}

export const apusReadWire = {
  schema_version: 1,
  symbol: 'APUS',
  generated_at: APUS_NOW,
  session_date: '2026-09-24',
  price: 5.37,
  prev_close: 2.29,
  change_pct: 1.345,
  followed: true,
  followed_note: null,
  setups: [
    {
      setup_type: 'first_pullback', state: 'watching', reason: 'no fresh leg', kind: null, chosen: false, level: 1,
      setup: null, forming: null, leg: null, last_price: 5.37, distance: null, grade: null, tape: null,
      window: botWindow, series,
    },
    {
      setup_type: 'bull_flag', state: 'leg', reason: 'pole +7.1%: wait for the flag', kind: 'bull_flag', chosen: true,
      level: 1, setup: null,
      forming: { trigger: 5.43, entry: 5.44, stop: 5.33, risk: 0.11, target1: 5.66, bars: 1, blocked: null,
        waiting: '1 more red or doji candle' },
      leg: { t: apusAt(15, 1), high: 5.45, low: 5.09, pct: 0.0707, bars: 3 },
      last_price: 5.37, distance: null, grade: null, tape: null, window: botWindow, series,
    },
    {
      setup_type: 'flat_top_breakout', state: 'watching', reason: 'the base ran past 6 candles without a break',
      kind: null, chosen: false, level: 0, setup: null, forming: null, leg: null, last_price: 5.37, distance: null,
      grade: null, tape: null, window: botWindow, series,
    },
    {
      setup_type: 'red_to_green', state: 'watching', reason: 'the 09:30-10:30 window closed', kind: null,
      chosen: false, level: 0, setup: null, forming: null, leg: null, last_price: 5.37, distance: null, grade: null,
      tape: null, window: { start: '09:30', end: '10:30', state: 'after' }, series,
    },
  ],
  no_scanner: [
    { setup_type: 'gap_and_go', label: 'Gap and Go', reason: 'No scanner yet: only its level is drawn (the premarket high).' },
    { setup_type: 'micro_pullback', label: 'Micro pullback', reason: 'Parked: it needs one-second bars.' },
  ],
  plan: {
    source: 'setup', setup_type: 'bull_flag', kind: 'bull_flag', state: 'forming', provisional: true, trigger: 5.43,
    entry: 5.44, stop: 5.33, target: 5.66, risk: 0.11, reward: 0.22, rr: 2.0,
    target_rule: 'the higher of entry + 2 x risk and the pole high', entry_rule: "1 cent over the last flag candle's high",
    stop_rule: "the flag's low", grade: null,
    reason: 'pole +7.1%: wait for the flag -- arms after 1 more red or doji candle', tape: null, flow: null,
    window: botWindow,
    checks: [
      { id: 'risk', state: 'ok', text: 'risk 0.11 within the 0.20 cap' },
      { id: 'macd', state: 'ok', text: '1-min MACD histogram +0.018' },
      { id: 'ema9', state: 'ok', text: 'above the 9 EMA 5.29' },
      { id: 'vwap', state: 'bad', text: 'under VWAP 6.09' },
      { id: 'in_way_round', state: 'warn', text: '$5.50 before the target' },
      { id: 'pulls', state: 'warn', text: 'bids being pulled (3 flags in the last minute)' },
      { id: 'window', state: 'warn', text: "outside the bot's 07:00-11:30 window: a hand trade" },
    ],
    marks: [{ price: 5.5, label: '$5.50', kind: 'round', size: null }],
  },
  levels: {
    hod: { price: 8.74, ts: apusAt(9, 32) }, pmh: 7.31, open: 6.99, prev_close: 2.29, vwap: 6.09,
    round_above: 5.5, round_below: 5.0,
  },
  groups: [
    { id: 'in_play', label: 'In play', question: 'Is this a stock people are trading right now?', verdict: 'ok', value: 'Yes',
      rows: [
        row('hod_today', 'HOD Momo today', '330 alerts since 08:31', 'ok', 'HOD Momo alert history'),
        row('catalyst', 'Catalyst', 'Contract / partnership · strong', 'ok', 'Catalyst verdict (Alpaca + Finnhub)'),
        row('rvol', 'Relative volume', '769x', 'ok', 'RVOL sensor'),
        row('ran_before', 'Has it run before?', '7 runs of +40% in a year', 'warn', 'Daily bars'),
      ] },
    { id: 'setups', label: 'Setups', question: 'Is a playbook setup forming, and what is it waiting for?', verdict: 'warn',
      value: 'Flag forming',
      rows: [
        row('lane_bull_flag', "Bull flag (bot's pick)", 'Forming · pole +7.1%: wait for the flag', 'warn',
          "The setup scanner's lanes (the template in play)", 'It arms after 1 more red or doji candle.'),
        row('lane_first_pullback', 'First pullback', 'Watching · no fresh leg', 'info', "The setup scanner's lanes (the template in play)"),
      ] },
    { id: 'front', label: 'Front side', question: 'Is momentum still up, or is it fading?', verdict: 'warn', value: 'Mixed',
      rows: [
        row('macd_1m', 'MACD 1-minute', 'hist +0.018 · line -0.015', 'ok', "The setup scanner's own 1-minute bars"),
        row('vwap', 'VWAP', '0.72 under 6.09 (-11.8%)', 'bad', 'Session VWAP from 04:00'),
        row('hod', 'High of day', '8.74 at 09:32 · 5 h 31 m ago', 'bad', 'HOD Momo high'),
      ] },
    { id: 'tape', label: 'Tape', question: 'What are Level 2 and the tape doing right now?', verdict: 'warn', value: 'Pulls',
      rows: [
        row('spread', 'Spread', '0.03 · 5.36 x 5.39 (0.6%)', 'ok', 'Level 2'),
        row('pulls', 'Pulled bids', '3 large bid levels pulled in 60 s', 'warn', 'Book watcher'),
      ] },
    { id: 'short', label: 'Short', question: 'Can shorts press it? Tight borrow means fewer sellers.', verdict: 'ok',
      value: 'No lend',
      rows: [row('borrow', 'Borrow (IBKR)', 'Nothing to lend since 08:58', 'ok', 'IBKR short-stock file')] },
    { id: 'float', label: 'Float', question: 'How many shares can trade?', verdict: 'unknown', value: 'Unknown',
      rows: [row('float', 'Float', 'Unknown', 'unknown', 'Yahoo fundamentals', 'Yahoo gave none.')] },
    { id: 'halts', label: 'Halts', question: 'What could stop me out or freeze me?', verdict: 'ok', value: 'No halts',
      rows: [
        row('halted', 'Halted now', 'No', 'ok', 'IBKR + Nasdaq halts'),
        row('halts_today', 'Halts today', 'None', 'ok', 'Halt log'),
      ] },
  ],
  counts: { ok: 9, warn: 5, bad: 2, unknown: 1, info: 1 },
};

export const apusDecisionsWire = {
  schema_version: 1,
  symbol: 'APUS',
  date: '2026-09-24',
  generated_at: APUS_NOW,
  summary: {
    text: 'The scanners saw 2 legs or poles and armed nothing. Why: risk 0.29 is over the 0.20 cap (x3). The bot did not trade it.',
    legs: 2, armed: 0, near: 0, triggered: 0, trades: 0,
    refusals: [{ reason: 'risk 0.29 is over the 0.20 cap', count: 3 }],
  },
  events: [
    { ts: apusAt(8, 31, 42), lane: 'hod_momo', event: 'alert', title: 'HOD Momo: Squeeze 5% at 2.84', detail: '14 of these today',
      count: 1, last_ts: null, levels: null },
    { ts: apusAt(9, 24), lane: 'first_pullback', event: 'leg', title: 'New high 7.23 on a 25.6% leg', detail: null, count: 1,
      last_ts: null, levels: { leg: { t: apusAt(9, 24), high: 7.23, low: 5.76, pct: 0.256 } } },
    { ts: apusAt(9, 26), lane: 'first_pullback', event: 'state', title: 'Not armed: risk 0.29 is over the 0.20 cap',
      detail: null, count: 3, last_ts: apusAt(9, 28), levels: null },
    { ts: apusAt(15, 1), lane: 'bull_flag', event: 'leg', title: 'Pole: 3 green candles, +7.1% to 5.45', detail: null,
      count: 1, last_ts: null, levels: { leg: { t: apusAt(15, 1), high: 5.45, low: 5.09, pct: 0.071, bars: 3 } } },
  ],
  sources: { journal: { ok: true, error: null }, hod_momo: { ok: true, error: null }, borrow: { ok: false, error: 'OSError: locked' } },
};

export const apusHistoryWire = {
  schema_version: 1,
  symbol: 'APUS',
  generated_at: APUS_NOW,
  daily: [
    { d: '2026-09-17', o: 1.6, h: 1.7, l: 1.55, c: 1.67, v: 900_000 },
    { d: '2026-09-18', o: 1.7, h: 2.68, l: 1.66, c: 1.8, v: 30_000_000 },
    { d: '2026-09-21', o: 1.8, h: 1.85, l: 1.7, c: 1.75, v: 2_000_000 },
    { d: '2026-09-22', o: 1.75, h: 2.4, l: 1.74, c: 2.2, v: 9_000_000 },
    { d: '2026-09-23', o: 2.2, h: 2.35, l: 2.1, c: 2.29, v: 3_000_000 },
    { d: '2026-09-24', o: 2.84, h: 8.74, l: 2.5, c: 5.37, v: 67_700_000 },
  ],
  runs: [
    { date: '2026-09-24', prior_close: 2.29, high: 8.74, close: 5.37, run_pct: 2.8166, close_pct: 1.345, today: true },
    { date: '2026-09-18', prior_close: 1.67, high: 2.68, close: 1.8, run_pct: 0.6048, close_pct: 0.0778, today: false },
  ],
  split: { factor: '1:10', ts: apusAt(9, 30) - 63 * 86400, reverse: true, days_ago: 63.2 },
  holdings: [
    row('setups', 'Setups armed', 'None in 365 days', 'info', 'The setups scoreboard (every template)'),
    row('boards', 'Days on the boards', 'Not kept per symbol yet', 'unknown', 'The leaderboard store'),
  ],
};
