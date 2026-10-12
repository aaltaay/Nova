/**
 * The calls while you hold (ADR 036 amendment 2026-10-01), pure: SELL NOW · FLUSH (trial T1's 30 s tape
 * reading, in trial; description only on Live), BROKE $X · NEXT Y with the raise it offers, and BIG SELLER
 * (#846: a size far over the book resting just past the price; BIG BUYER on the bid for a short) with its
 * end -- taken, pulled, out of view. The stop and target calls stay `momentModel`'s; these come after them.
 * A big seller is shown, never acted on: no order, no stop move, no gate.
 */
import { bigLine, pickWall } from './bigSeller';
import { NOVA_CALL_SEC, STOCK_READ_FLUSH_AFTER_SEC } from './constants';
import { rowOf } from './heldRead';
import type { MomentCall, MomentInputs } from './momentModel';
import { fmtPx } from './planMath';

/** A flush reading older than this is not a call. */
const FLUSH_FRESH_SEC = 3;

export interface HeldCall {
  call: MomentCall;
  /** The moment's badge while the call shows; null keeps the badge it had. */
  badge: string | null;
  /** When what it says happened (epoch seconds): of two calls, the corner says the newer. */
  at?: number;
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
      badge: 'FLUSH · IN TRIAL T1', at: f.at,
      call: { id, tone: 'wait', title: 'FLUSH ON THE TAPE · IN TRIAL T1', ping: false, pin: null,
        detail: `Sellers flushed the tape${score}. On Live this is a description only until trial T1 reads.` },
    };
  }
  return {
    badge: 'SELL NOW · FLUSH', at: f.at,
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
    badge: `BROKE $${up.round.toFixed(2)}${nextWords}`, at: up.at,
    call: {
      id: `broke:${h.since ?? 0}:${up.round}`, tone: 'go', title: `BROKE $${up.round.toFixed(2)}${nextWords}`,
      detail: `${up.text}? A candle closed over $${up.round.toFixed(2)}; only a close moves a stop. Raise stop on the `
        + 'plan box sets it.',
      pin: { label: `BROKE $${up.round.toFixed(2)}`, price: up.round, at: up.at }, ping: true,
    },
  };
}

/** BIG SELLER (BIG BUYER for a short, on the bid): the nearest one resting just past the price, pinned at its
 * price, one ping when it is called; then how it ended, while the reading still carries it. It keeps the
 * moment's badge. Null without a fresh read: the held card's own line says why. */
export function bigCall(i: MomentInputs, short: boolean): HeldCall | null {
  const r = i.big ?? null;
  if (!r || !r.watching) return null;
  const w = pickWall(short ? r.buyers : r.sellers);
  if (!w) return null;
  const line = bigLine(r, short);
  const there = w.state === 'holding' || w.state === 'left';
  return {
    badge: null,
    at: there ? w.calledTs ?? w.firstSeenTs : w.endedTs ?? 0,
    call: {
      id: there ? `big:${w.id}` : `big-${w.state}:${w.id}`, tone: there ? 'wait' : 'info', title: line.text,
      detail: line.detail, pin: there ? { label: short ? 'BIG BUYER' : 'BIG SELLER', price: w.price, at: null } : null,
      ping: there,
    },
  };
}

/** Of two calls, the one about what happened last. */
export function newerCall(a: HeldCall | null, b: HeldCall | null): HeldCall | null {
  if (!a || !b) return a ?? b;
  return (b.at ?? 0) > (a.at ?? 0) ? b : a;
}

/** The flush first (a tape call is about now), then the newer of a raise and a big seller's word; null when
 * none is due. */
export function heldCall(i: MomentInputs): HeldCall | null {
  const flush = flushCall(i);
  if (flush) return flush;
  const up = raiseCall(i);
  const raise = up && i.now - up.call.pin!.at! <= NOVA_CALL_SEC * 20 ? up : null;
  return newerCall(raise, bigCall(i, false));
}
