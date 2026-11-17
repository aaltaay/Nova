/** The brain as the backend answers it, for the tests (the approved mockup's XLAB example). */
import { readBrainSeat } from './brainSeatApi';
import type { BrainSeatStatus } from './types';

/** 2026-11-13 10:41 ET, a Friday. */
export const BRAIN_NOW = 1_794_584_460;

/** The brain's TRADER on the wire: On, in XLAB, as the mockup's panel draws it. */
export function brainTrader(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: 'brain', on: true, at: BRAIN_NOW - 3_600, can_turn_on: true, why_not_on: null, done_for_today: false,
    state: 'in_trade', text: 'Brain · In XLAB +$42.00', symbol: 'XLAB',
    lane: { symbol: 'XLAB', depth: true, tape: true, why: 'First pullback holding the 4.30 bid' },
    position: { symbol: 'XLAB', qty: 200, avg_cost: 4.32, mark: 4.53, unrealized_pnl: 42 },
    handed: [],
    today: { pnl: 42, loss_limit_usd: -500, tripped_at: null },
    limits: { max_shares: 1000, risk_usd: 150, budget_usd: 25_000, budget_used_usd: 906, flat_by: '15:55' },
    note: {
      text: 'Held the 4.30 bid three times with buyers lifting 4.32. Bought 200 at 4.32, stop 4.19.', at: BRAIN_NOW,
    },
    connected: true,
    reading: [
      { symbol: 'XLAB', text: 'First pullback, go', source: 'lane' },
      { symbol: 'SSII', text: '5-minute flat top, 3 touches', source: 'level1' },
      { symbol: 'RUNR', text: 'Bull flag forming', source: 'level1' },
    ],
    events: [{ at: BRAIN_NOW, kind: 'fill', symbol: 'XLAB', text: 'bought 200 XLAB at 4.32' }],
    ...over,
  };
}

/** `GET /api/traders` with that brain. */
export function tradersAnswer(over: Record<string, unknown> = {}, top: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1, generated_at: BRAIN_NOW, venue: 'paper',
    traders: { claude: { name: 'claude', on: false, state: 'off', text: 'Claude · Off' }, brain: brainTrader(over) },
    error: null,
    ...top,
  };
}

/** The same brain as the desk reads it. */
export function brainStatus(over: Record<string, unknown> = {}, top: Record<string, unknown> = {}): BrainSeatStatus {
  const status = readBrainSeat(tradersAnswer(over, top));
  if (!status) throw new Error('the fixture is not the traders view');
  return status;
}

/** The mockup's other header states. */
export const BRAIN_OFF = {
  on: false, state: 'off', text: 'Brain · Off', symbol: null, position: null, note: null, reading: [], events: [],
  lane: { symbol: null, depth: false, tape: false, why: null }, today: { pnl: 0, loss_limit_usd: -500, tripped_at: null },
};
export const BRAIN_WATCHING = {
  state: 'watching', text: 'Brain · Watching SSII', symbol: 'SSII', position: null,
  lane: { symbol: 'SSII', depth: true, tape: true, why: '5-minute flat top' },
  today: { pnl: 0, loss_limit_usd: -500, tripped_at: null },
};
export const BRAIN_DONE = {
  ...BRAIN_OFF, state: 'done', done_for_today: true, can_turn_on: false, text: 'Brain · Done for today -$500.00',
  why_not_on: { reason: 'TRADER_DAY_STOP', error: 'The brain reached its day stop today: it stays Off until tomorrow.' },
  today: { pnl: -500, loss_limit_usd: -500, tripped_at: BRAIN_NOW - 60 },
};
export const BRAIN_HANDED = {
  ...BRAIN_OFF, text: 'Brain · Off · XLAB is yours to close', handed: [{ symbol: 'XLAB', qty: 200, stop_price: 4.19 }],
};
