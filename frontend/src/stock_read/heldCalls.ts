/**
 * The calls while you hold (ADR 036 amendment 2026-10-01), pure: SELL NOW · FLUSH (trial T1's 30 s tape
 * reading, in trial; description only on Live) and BROKE $X · NEXT Y with the raise it offers. The stop
 * and target calls stay `momentModel`'s; these come after them.
 */
import { NOVA_CALL_SEC, STOCK_READ_FLUSH_AFTER_SEC } from './constants';
import { rowOf } from './heldRead';
import type { MomentCall, MomentInputs } from './momentModel';
import { fmtPx } from './planMath';

/** A flush reading older than this is not a call. */
const FLUSH_FRESH_SEC = 3;

export interface HeldCall {
  call: MomentCall;
  badge: string;
}

function flushCall(i: MomentInputs): HeldCall | null {
  const f = i.flush ?? null;
  if (!f || f.label !== 'flush' || i.held.since === null) return null;
  if (i.now - i.held.since < STOCK_READ_FLUSH_AFTER_SEC || i.now - f.at > FLUSH_FRESH_SEC) return null;
  const score = f.score !== null ? ` (30 s score ${f.score.toFixed(2)})` : '';
  const live = (i.who?.venue ?? null) === 'live';
  // One call (and one ping) per flush: readings a few seconds apart are the same flush.
  const id = `flush:${i.held.since}:${Math.floor(f.at / 15)}`;
  if (live) {
    return {
      badge: 'FLUSH · IN TRIAL T1',
      call: { id, tone: 'wait', title: 'FLUSH ON THE TAPE · IN TRIAL T1', ping: false, pin: null,
        detail: `Sellers flushed the tape${score}. On Live this is a description only until trial T1 reads.` },
    };
  }
  return {
    badge: 'SELL NOW · FLUSH',
    call: { id, tone: 'stop', title: 'SELL NOW · FLUSH · IN TRIAL T1', ping: true,
      pin: i.last !== null ? { label: 'FLUSH', price: i.last, at: f.at } : null,
      detail: `Sellers flushed the tape${score}. Trial T1 measures whether selling here pays: in sample it halved `
        + 'full stops and shook out about 2 in 5 trades that would have reached their target. A call, never an order.' },
  };
}

function raiseCall(i: MomentInputs): HeldCall | null {
  const h = i.read?.held ?? null;
  const up = h?.raise ?? null;
  if (!h || !up || h.stop?.source === 'nova') return null;   // Nova raises its own stop and says so
  const next = rowOf(h, 'next');
  const nextWords = next ? ` · NEXT ${fmtPx(next.price)}` : '';
  return {
    badge: `BROKE $${up.round.toFixed(2)}${nextWords}`,
    call: {
      id: `broke:${h.since ?? 0}:${up.round}`, tone: 'go', title: `BROKE $${up.round.toFixed(2)}${nextWords}`,
      detail: `${up.text}? A candle closed over $${up.round.toFixed(2)}; only a close moves a stop. Raise stop on the `
        + 'plan box sets it.',
      pin: { label: `BROKE $${up.round.toFixed(2)}`, price: up.round, at: up.at }, ping: true,
    },
  };
}

/** The flush first (a tape call is about now), then a raise; null when neither is due. */
export function heldCall(i: MomentInputs): HeldCall | null {
  const flush = flushCall(i);
  if (flush) return flush;
  const up = raiseCall(i);
  if (up && i.now - up.call.pin!.at! <= NOVA_CALL_SEC * 20) return up;
  return null;
}
