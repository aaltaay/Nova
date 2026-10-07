/**
 * A short you hold, on the 1-minute chart (ADR 048, #778 step 3): the moment ladder mirrored, pure.
 *
 * - The badge reads "SHORT 416 · BROKE $5.50 · NEXT 5.35" while a 1-minute candle closed under a round and the
 *   read offers to lower the buy stop, else "SHORT 416 · +$124.80".
 * - The buy stop printing (a price at or over it) or the cover target trading (at or under it) calls COVER NOW.
 * - The track reads Forming · Trigger · Short · Your cover.
 *
 * Nova's own short (#778 step 5) -- the bot's, Auto-entry's or an approved bracket's -- says what Nova sent, what
 * filled, what rests at the broker and how it ended: BOT SHORTING, BOT SHORTED, BOT IS COVERING, COVERED.
 *
 * Trial T1's flush call is a long's (sellers flushing the tape); no trial reads a short's mirror, so none is
 * called here.
 */
import { NOVA_CALL_SEC } from './constants';
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
  type MomentCall,
  type MomentInputs,
} from './momentModel';
import { fmtPx } from './planMath';
import { hhmmssEt } from './timeWords';
import type { StockModeTrade } from './types';

const EPS = 1e-9;

function recent(ts: number | null, now: number): boolean {
  return ts !== null && now - ts >= -1 && now - ts <= NOVA_CALL_SEC;
}

function ttlWords(ttl: number | null): string {
  return ttl !== null ? `${ttl} s` : 'the sleeve\'s time limit';
}

/** Nova's short entry still working (#778 step 5): the bot's, Auto-entry's or an approved bracket's. */
export function enteringShort(t: StockModeTrade, ttl: number | null): Moment {
  const size = `${t.qty ?? '?'} @ ${fmtPx(t.entry)}`;
  const stop = fmtPx(t.stop);
  const words: Record<StockModeTrade['kind'], [string, string]> = {
    auto_entry: [`BOT SHORTING · ${size}`, `Nova sent the short at ${hhmmssEt(t.sent_at)} with its buy stop ${stop}. `
      + `Unfilled after ${ttlWords(ttl)}, both are cancelled. Every cover is yours.`],
    approve: [`SENT · SHORT ${size}`, `The short went with its buy stop ${stop} and cover ${fmtPx(t.target)}. `
      + `Unfilled after ${ttlWords(ttl)}, all three are cancelled.`],
    bot: [`BOT SHORTING · ${size}`, `The bot sent its short with its buy stop ${stop} and cover ${fmtPx(t.target)}; it `
      + `covers at one of them or after 15 minutes. Unfilled after ${ttlWords(ttl)}, it is cancelled.`],
    exit: ['BOT HOLDS THE COVER', `Nova's buy stop ${stop} rests at the broker.`],
  };
  const [badge, detail] = words[t.kind];
  return {
    step: 1, side: 'short', exitLabel: t.exits === 'nova' ? 'Target / stop' : 'Your cover', tone: 'go', badge,
    track: true,
    call: {
      id: `sent:${t.entry_order_id ?? t.sent_at}`, tone: 'nova', title: badge, detail,
      pin: t.entry === null ? null : { label: t.kind === 'approve' ? 'SENT' : 'BOT SHORTING', price: t.entry, at: t.sent_at },
      ping: false,
    },
  };
}

/** Nova's short just filled: what rests at the broker now. */
function shortedCall(i: MomentInputs, t: StockModeTrade | null): MomentCall | null {
  if (!t || t.state !== 'holding' || !recent(t.filled_at, i.now)) return null;
  const fill = `${t.qty ?? '?'} @ ${fmtPx(t.fill_price)}`;
  const stop = fmtPx(t.stop);
  const words: Record<StockModeTrade['kind'], [string, string, string]> = {
    auto_entry: [`BOT SHORTED ${fill}`, 'BOT SHORTED', `Its buy stop ${stop} rests at the broker. The cover is yours.`],
    approve: [`SHORTED ${fill}`, 'SHORTED', `The buy stop ${stop} and the cover ${fmtPx(t.target)} are working at the `
      + 'broker. The first one hit cancels the other.'],
    bot: [`BOT SHORTED ${fill}`, 'BOT SHORTED', `The buy stop ${stop} and the cover ${fmtPx(t.target)} rest at the `
      + 'broker; the first one hit cancels the other. The bot covers after 15 minutes if neither fills.'],
    exit: ['BOT TOOK THE COVER', 'BOT COVER', `Nova's buy stop ${stop} rests at the broker. Take it back any time.`],
  };
  const [title, pill, detail] = words[t.kind];
  return {
    id: `shorted:${t.entry_order_id ?? t.filled_at}`, tone: 'nova', title, detail,
    pin: t.fill_price === null ? null : { label: pill, price: t.fill_price, at: t.filled_at }, ping: true,
  };
}

/** Nova's short that ended on the plan's own setup (or so recently its call still shows). */
function finishedShortTrade(i: MomentInputs): StockModeTrade | null {
  const t = i.who?.trade ?? null;
  if (!t || t.side !== 'short' || (t.state !== 'closed' && t.state !== 'missed')) return null;
  if (t.state === 'missed') return recent(t.closed_at, i.now) ? t : null;
  const same = t.setup_id !== null && t.setup_id === (i.read?.plan?.setup_id ?? null);
  return same || recent(t.closed_at, i.now) ? t : null;
}

/** How Nova's short ended: covered at its cover, stopped over its buy stop, timed out, or missed. */
function finishedShort(i: MomentInputs, t: StockModeTrade): Moment {
  const exitLabel = t.exits === 'nova' ? 'Target / stop' : 'Your cover';
  if (t.state === 'missed') {
    const again = t.kind === 'approve' ? '' : ' A miss gives the day\'s trade back: the bot may trade the next go trigger.';
    return {
      step: 1, side: 'short', exitLabel, tone: 'wait', badge: 'THE BOT\'S SHORT MISSED', track: true,
      call: {
        id: `missed:${t.entry_order_id ?? t.sent_at}`, tone: 'wait', title: 'THE BOT\'S SHORT MISSED',
        detail: `${t.qty ?? '?'} @ ${fmtPx(t.entry)} did not fill in ${ttlWords(i.ttlSec)} and was cancelled.${again}`,
        pin: null, ping: false,
      },
    };
  }
  // A short makes money as the price falls (ADR 048).
  const pnl = t.exit_price !== null && t.fill_price !== null && t.qty !== null ? (t.fill_price - t.exit_price) * t.qty : null;
  const money = pnl !== null ? ` · ${fmtPnl(pnl)}` : '';
  const exit = fmtPx(t.exit_price);
  const said: Record<string, [string, string]> = {
    target: [`COVERED ${exit}${money}`, t.kind === 'bot' ? 'The bot\'s cover filled.'
      : 'The cover filled at the broker; the buy stop was cancelled.'],
    stop: [`STOPPED ${exit}${money}`, t.kind === 'bot' ? 'The bot covered at its buy stop.'
      : 'The buy stop filled at the broker; the cover was cancelled.'],
    time: [`TIME STOP ${exit}${money}`, 'The bot covered after 15 minutes in the trade.'],
    flush: [`COVERED ${exit}${money}`, 'The bot covered on a burst of buying.'],
  };
  const [badge, detail] = said[t.exit_reason ?? ''] ?? [`FLAT${money}`, 'The short was covered outside Nova\'s orders.'];
  const fresh = recent(t.closed_at, i.now);
  const tone = t.exit_reason === 'stop' ? 'stop' : 'done';
  return {
    step: fresh ? 3 : 4, side: 'short', exitLabel, tone, badge: fresh ? badge : `FLAT${money}`, track: true,
    call: fresh ? {
      id: `closed:${t.setup_id ?? t.entry_order_id}:${t.closed_at}`, tone, title: badge, detail,
      pin: t.exit_reason === 'target' && t.exit_price !== null ? { label: `COVERED ${exit}`, price: t.exit_price, at: t.closed_at }
        : null,
      ping: t.exit_reason === 'target' || t.exit_reason === 'stop' || t.exit_reason === 'time',
    } : null,
  };
}

/** Shares held short (a positive count): the account's short, or Nova's live short trade. */
export function shortQty(i: MomentInputs): number {
  const own = i.position && i.position.qty < 0 ? -i.position.qty : 0;
  const t = i.who?.trade ?? null;
  const nova = t && t.state === 'holding' && t.side === 'short' && t.qty !== null ? t.qty : 0;
  return Math.max(own, nova);
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
function lowerCall(i: MomentInputs, qty: number): { badge: string; call: MomentCall } | null {
  const h = i.read?.held ?? null;
  const down = h?.lower ?? null;
  if (!h || h.side !== 'short' || !down || h.stop?.source === 'nova') return null;   // Nova lowers its own and says so
  if (i.now - down.at > NOVA_CALL_SEC * 20) return null;
  const next = rowOf(h, 'next');
  const nextWords = next ? ` · NEXT ${fmtPx(next.price)}` : '';
  const broke = `BROKE $${down.round.toFixed(2)}${nextWords}`;
  return {
    badge: `SHORT ${qty} · ${broke}`,
    call: {
      id: `broke-short:${h.since ?? 0}:${down.round}`, tone: 'go', title: broke,
      detail: `${down.text}? A candle closed under $${down.round.toFixed(2)}; only a close moves a stop. Lower stop on `
        + 'the plan box sets it.',
      pin: { label: `BROKE $${down.round.toFixed(2)}`, price: down.round, at: down.at }, ping: true,
    },
  };
}

/** The moment while you hold ``qty`` shares short. */
export function holdingShort(i: MomentInputs, qty: number): Moment {
  const lv = judgedLevels(i);
  const t = i.who?.trade ?? null;
  const nova = t && t.state === 'holding' && t.side === 'short' ? t : null;
  const cost = i.position?.avgCost ?? nova?.fill_price ?? null;
  const last = i.last ?? i.read?.price ?? null;
  const pnl = cost !== null && last !== null ? (cost - last) * qty : null;
  const track = lv !== null || nova !== null || i.read?.plan?.source === 'setup';
  const inTrade = `SHORT ${qty}${pnl !== null ? ` · ${fmtPnl(pnl)}` : ''}`;
  if (nova?.kind === 'exit') {
    return { step: 2, exitLabel: 'Target / stop', side: 'short', tone: 'holding', track,
      badge: `BOT HOLDS THE COVER${pnl !== null ? ` · ${fmtPnl(pnl)}` : ''}`, call: null };
  }
  if (nova && nova.exits === 'nova') {
    // The bot's short or an approved bracket (#778 step 5): its buy stop and cover rest at the broker.
    if (nova.exiting) {
      return {
        step: 3, exitLabel: 'Target / stop', side: 'short', tone: 'target', badge: 'BOT IS COVERING', track,
        call: { id: `exiting:${nova.setup_id ?? nova.entry_order_id}`, tone: 'nova', title: 'BOT IS COVERING',
          detail: 'The bot is covering: its cover, its buy stop or its 15 minutes came.', pin: null, ping: false },
      };
    }
    return { step: 2, exitLabel: 'Target / stop', side: 'short', tone: 'holding', badge: inTrade, track,
      call: shortedCall(i, nova) };
  }
  // Auto-entry's short (#778 step 5): its buy stop rests at the broker; the cover is yours.
  const resting = nova?.kind === 'auto_entry' && nova.stop_order_id !== null;
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
        detail: `${printed} ${nobody(which, resting, nova)}${atStop}`,
        pin: last === null ? null : { label: 'COVER NOW', price: last, at }, ping: true,
      },
    };
  }
  const said = lowerCall(i, qty);
  return { step: 2, exitLabel: 'Your cover', side: 'short', tone: 'holding', badge: said?.badge ?? inTrade, track,
    call: said?.call ?? shortedCall(i, nova) };
}

/** Who covers once a level is hit: the buy stop resting at the broker, or you. */
function nobody(which: 'target' | 'stop', resting: boolean, nova: StockModeTrade | null): string {
  if (which === 'stop' && resting) return 'Its buy stop rests at the broker and covers it there.';
  return nova?.kind === 'auto_entry' ? 'Nova will not cover: the cover is yours.' : 'No order is working: the cover is yours.';
}

/** Shares held either way, as a count: a long's or a short's. */
export function heldAnyQty(i: MomentInputs): number {
  return heldQty(i) || shortQty(i);
}

/** `momentOf`, with a short you hold (and no long) as the short's moment, and Nova's own short -- working,
 * held or just ended -- said the short's way (#778 step 5). */
export function momentOfSides(i: MomentInputs): Moment | null {
  const t = i.who?.trade ?? null;
  if (t?.side === 'short' && t.state === 'entering') return enteringShort(t, i.ttlSec);
  if (heldQty(i) === 0 && t?.state !== 'entering') {
    const qty = shortQty(i);
    if (qty > 0) return holdingShort(i, qty);
    const done = finishedShortTrade(i);
    if (done) return finishedShort(i, done);
  }
  return momentOf(i);
}

/** `nextHeld`, with a short you hold judged the short's way. */
export function nextHeldSides(prev: HeldMemory, i: MomentInputs): HeldMemory {
  if (heldQty(i) === 0 && shortQty(i) > 0) return nextHeldShort(prev, i);
  return nextHeld(prev, i);
}
