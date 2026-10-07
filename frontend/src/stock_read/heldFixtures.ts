/** The read's `held` on the operator's APUS Paper trade, 2026-09-24 08:59:05: 100 shares at 5.075, the price
 * 6.64; the 08:58 candle closed 6.46 over $6.00 and the 08:56 one 5.59 over $5.50; the 08:57 high 6.66
 * crossed $6.50 with no close over it; the stop 5.45 (raised at 08:57). Test data only. */
const T0859 = 1_790_254_740;   // 2026-09-24 08:59:00 ET

export const APUS_HELD_SINCE = 1_790_253_888;   // 08:44:48, the first buy

export const apusHeldWire = {
  schema_version: 1,
  qty: 100,
  avg: 5.075,
  price: 6.64,
  open_usd: 156.5,
  r: 3.52,
  risk: 0.445,
  since: APUS_HELD_SINCE,
  stop: { price: 5.45, source: 'yours', rule: 'your stop', printed: false },
  raise: { to: 5.95, round: 6.0, at: T0859, text: 'Raise the stop to 5.95, 5c under $6.00' },
  target: { price: 5.965, rule: 'your average + 2 x 0.445', traded_at: T0859 - 180 },
  ladder: [
    { role: 'then', price: 7.5, text: '$7.50', r: 5.45, usd: 242.5 },
    { role: 'next', price: 6.97, text: 'HOD 6.97 · $7.00', r: 4.26, usd: 189.5 },
    { role: 'now', price: 6.64, text: '+156.50 open', r: 3.52, usd: 156.5 },
    { role: 'through', price: 6.5, text: 'traded through at 08:57, no candle closed over it yet', r: null, usd: null },
    { role: 'broke', price: 6.0, text: 'the 08:58 candle closed 6.46 over it', r: null, usd: null },
    { role: 'broke', price: 5.5, text: 'the 08:56 candle closed 5.59 over it', r: null, usd: null },
    { role: 'stop', price: 5.45, text: 'your stop', r: 0.84, usd: 37.5 },
    { role: 'cost', price: 5.075, text: 'your average, 100 sh', r: 0, usd: 0 },
  ],
  broke: [{ round: 6.0, at: T0859, close: 6.46 }, { round: 5.5, at: T0859 - 120, close: 5.59 }],
  through: [{ round: 6.5, at: T0859 - 120, high: 6.66 }],
  levels: {
    room: { state: 'info', text: '0.7R to HOD 6.97, from the price', detail: null, trial: null },
    target: { state: 'ok', text: '5.97 (2R) traded at 08:56: you are past it', detail: null },
    stop: { state: 'ok', text: '5.45 is 5c under $5.50', detail: null },
    next: { state: 'info', text: '$7.00 is 36c above: resistance until it prints through, a trigger after', detail: null },
    recent: { state: 'ok', text: 'Broke $6.00: the 08:58 candle closed 6.46', detail: null },
  },
  checks: [
    { id: 'spread', state: 'ok', text: 'the spread 0.03 is within half the 1.19 risk' },
    { id: 'macd', state: 'ok', text: '1-min MACD histogram +0.062' },
    { id: 'vwap', state: 'ok', text: 'above VWAP 4.92' },
  ],
};

export const APUS_HELD_NOW = T0859 + 5;

/** The read's `held` on a short (ADR 048), test data only: 416 RDYN short at 5.77 since 10:15 ET, the price 5.46,
 * your buy stop 5.89; the 10:31 candle closed 5.44 under $5.50, so the stop may come down to 5.55. */
const T1032 = 1_791_383_520;   // 2026-10-07 10:32:00 ET

export const RDYN_SHORT_SINCE = 1_791_382_500;   // 10:15:00, the short's fill

export const rdynShortWire = {
  schema_version: 1,
  side: 'short',
  qty: 416,
  avg: 5.77,
  price: 5.46,
  open_usd: 128.96,
  r: 2.58,
  risk: 0.12,
  since: RDYN_SHORT_SINCE,
  stop: { price: 5.89, source: 'yours', rule: 'your buy stop', printed: false },
  raise: null,
  lower: { to: 5.55, round: 5.5, at: T1032, text: 'Lower the stop to 5.55, 5c over $5.50' },
  target: { price: 5.53, rule: 'your average - 2 x 0.12', traded_at: T1032 - 60 },
  ladder: [
    { role: 'stop', price: 5.89, text: 'your buy stop', r: -1, usd: -49.92 },
    { role: 'cost', price: 5.77, text: 'your average, 416 sh short', r: 0, usd: 0 },
    { role: 'broke', price: 5.5, text: 'the 10:31 candle closed 5.44 under it', r: null, usd: null },
    { role: 'now', price: 5.46, text: '+128.96 open', r: 2.58, usd: 128.96 },
    { role: 'next', price: 5.35, text: 'bottom ×2', r: 3.5, usd: 174.72 },
    { role: 'then', price: 5.0, text: '$5.00 · open', r: 6.42, usd: 320.32 },
  ],
  broke: [{ round: 5.5, at: T1032, close: 5.44 }],
  through: [],
  levels: {
    room: { state: 'info', text: '0.9R to 5.35, from the price', detail: null, trial: null },
    target: { state: 'ok', text: '5.53 (2R) traded at 10:31: you are past it', detail: null },
    stop: { state: 'ok', text: '5.89 is 9c over $5.80', detail: null },
    next: { state: 'info', text: '$5.00 is 46c below: support until it prints through, a trigger after', detail: null },
    recent: { state: 'ok', text: 'Lost $5.50: the 10:31 candle closed 5.44', detail: null },
  },
  checks: [{ id: 'spread', state: 'ok', text: 'the spread 0.01 is within half the 0.12 risk' }],
};

export const RDYN_SHORT_NOW = T1032 + 5;
