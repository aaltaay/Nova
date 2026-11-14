/**
 * A short you hold, on the 1-minute chart (ADR 048, #778 step 3): the moment ladder mirrored, pure.
 *
 * - The badge reads "SHORT 416 · BROKE $5.50 · NEXT 5.35" while a 1-minute candle closed under a round and the
 *   read offers to lower the buy stop, else "SHORT 416 · +$124.80".
 * - The buy stop printing (a price at or over it) or the cover target trading (at or under it) calls COVER NOW.
 * - The track reads Forming · Trigger · Short · Your cover.
 *
 * The short is the operator's own: Nova shorts nothing by itself (ADR 072). Trial T1's flush call is a long's
 * (sellers flushing the tape); no trial reads a short's mirror, so none is called here.
 */
import { plainPrice } from '../utils/priceTick';
import { BROKE_CALL_SEC } from './constants';
import { bigCall, newerCall, type HeldCall } from './heldCalls';
import { rowOf } from './heldRead';
import {
  fmtPnl,
  heldQty,
  judgedLevels,
  momentOf,
  nextHeld,
  NO_HELD,
  type HeldMemory,
  type Moment,
  type MomentInputs,
} from './momentModel';
import { fmtPx } from './planMath';
import { hhmmssEt } from './timeWords';

const EPS = 1e-9;

/** Shares the account holds short (a positive count). */
export function shortQty(i: MomentInputs): number {
  return i.position && i.position.qty < 0 ? -i.position.qty : 0;
}

/** The memory after one more look at a held short: the stop prints at or over it, the target at or under. */
export function nextHeldShort(prev: HeldMemory, i: MomentInputs): HeldMemory {
  let next: HeldMemory = prev.since === null ? { ...NO_HELD, since: i.now } : prev;
  const lv = judgedLevels(i, next);
  const last = i.last ?? i.read?.price ?? null;
  if (lv && (lv.stop ?? null) !== (next.stopFor ?? null)) next = { ...next, stopAt: null, stopFor: lv.stop };
  if (lv && (lv.target ?? null) !== (next.targetFor ?? null)) next = { ...next, targetAt: null, targetFor: lv.target };
  if (last !== null && lv) {
    if (lv.target !== null && next.targetAt === null && last <= lv.target + EPS) next = { ...next, targetAt: i.now };
    if (lv.stop !== null && next.stopAt === null && last >= lv.stop - EPS) next = { ...next, stopAt: i.now };
  }
  return next;
}

function due(held: HeldMemory): 'target' | 'stop' | null {
  if (held.targetAt === null && held.stopAt === null) return null;
  if (held.stopAt === null) return 'target';
  if (held.targetAt === null) return 'stop';
  return held.stopAt >= held.targetAt ? 'stop' : 'target';
}

/** BROKE $X · NEXT Y: a candle closed under a round, and the buy stop may come down over it. */
function lowerCall(i: MomentInputs, qty: number): HeldCall | null {
  const h = i.read?.held ?? null;
  const down = h?.lower ?? null;
  if (!h || h.side !== 'short' || !down || h.stop?.source === 'nova') return null;   // Nova's own resting stop is not yours to lower
  if (i.now - down.at > BROKE_CALL_SEC) return null;
  const next = rowOf(h, 'next');
  const nextWords = next ? ` · NEXT ${fmtPx(next.price)}` : '';
  const broke = `BROKE $${down.round.toFixed(2)}${nextWords}`;
  return {
    badge: `SHORT ${qty} · ${broke}`, at: down.at,
    call: {
      id: `broke-short:${h.since ?? 0}:${down.round}`, tone: 'go', title: broke,
      detail: `${down.text}? A candle closed under $${plainPrice(down.round)}; only a close moves a stop. Lower stop on `
        + 'the plan box sets it.',
      pin: { label: `BROKE $${plainPrice(down.round)}`, price: down.round, at: down.at }, ping: true,
    },
  };
}

/** The moment while you hold ``qty`` shares short. */
export function holdingShort(i: MomentInputs, qty: number): Moment {
  const lv = judgedLevels(i);
  const cost = i.position?.avgCost ?? null;
  const last = i.last ?? i.read?.price ?? null;
  const pnl = cost !== null && last !== null ? (cost - last) * qty : null;
  const track = lv !== null || i.read?.plan?.source === 'setup';
  const inTrade = `SHORT ${qty}${pnl !== null ? ` · ${fmtPnl(pnl)}` : ''}`;
  const which = due(i.held);
  const level = which && lv ? (which === 'target' ? lv.target : lv.stop) : null;
  if (which && level !== null) {
    const word = which === 'target' ? 'TARGET ↓' : 'STOP ↑';
    const at = which === 'target' ? i.held.targetAt : i.held.stopAt;
    const printed = which === 'target'
      ? `${fmtPx(level)} or lower traded at ${hhmmssEt(at)}.`
      : `${fmtPx(level)} or higher printed at ${hhmmssEt(at)}.`;
    const atStop = which === 'stop' && cost !== null && lv?.stop != null
      ? ` At the stop the short is about ${fmtPnl((cost - lv.stop) * qty)}.` : '';
    return {
      step: 3, exitLabel: 'Your cover', side: 'short', tone: which, badge: `${word} ${fmtPx(level)} HIT · COVER`, track,
      call: {
        id: `cover-${which}:${i.held.since ?? 0}:${level}`, tone: which, title: `COVER NOW · ${word} ${fmtPx(level)}`,
        detail: `${printed} No order is working: the cover is yours.${atStop}`,
        pin: last === null ? null : { label: 'COVER NOW', price: last, at }, ping: true,
      },
    };
  }
  // The newer of a lowered stop's offer and a big buyer on the bid (#846: shown, never acted on).
  const said = newerCall(lowerCall(i, qty), bigCall(i, true));
  return { step: 2, exitLabel: 'Your cover', side: 'short', tone: 'holding', badge: said?.badge ?? inTrade, track,
    call: said?.call ?? null };
}

/** Shares held either way, as a count: a long's or a short's. */
export function heldAnyQty(i: MomentInputs): number {
  return heldQty(i) || shortQty(i);
}

/** `momentOf`, with a short you hold (and no long) as the short's moment. */
export function momentOfSides(i: MomentInputs): Moment | null {
  if (heldQty(i) === 0) {
    const qty = shortQty(i);
    if (qty > 0) return holdingShort(i, qty);
  }
  return momentOf(i);
}

/** `nextHeld`, with a short you hold judged the short's way. */
export function nextHeldSides(prev: HeldMemory, i: MomentInputs): HeldMemory {
  if (heldQty(i) === 0 && shortQty(i) > 0) return nextHeldShort(prev, i);
  return nextHeld(prev, i);
}
