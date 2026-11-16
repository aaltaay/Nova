/**
 * The trade's moment on the 1-minute chart (ADR 037), pure: where the setup and the operator's position stand --
 * the badge and its track (Forming, Trigger, Holding, then your exit) -- and the call in the chart's corner:
 * ENTER NOW, SELL NOW, or what the tape says while you hold, with the id its one ping keys on. Every price is the
 * read's or the position's own; nothing is estimated. Nova trades nothing here: the strategies only watch (ADR 072).
 *
 * maintainer: one-concern the moment ladder and its calls must be judged in one place, so the badge, the
 * track, the call and its ping can never disagree about where the trade stands.
 */
import type { BigWalls } from './bigSeller';
import { ENTER_NOW_RISK_SHARE, ENTER_NOW_SEC } from './constants';
import { heldCall } from './heldCalls';
import { fmtPx, fmtStep, planBadge, planLane, setupName, sizeFor } from './planMath';
import { notATrade, resultBadge, thinPlan } from './planVerdict';
import { actWords, enterWord, nearSide, shortWaitingWords } from './momentWords';
import { hhmmssEt } from './timeWords';
import type { SetupLane, StockPlan, StockRead } from './types';

const EPS = 1e-9;

/** The levels the operator's own position is judged by, kept for the whole holding episode. */
export interface HeldLevels {
  entry: number | null;
  stop: number;
  target: number;
  key: string | null;
}

/** This tab's memory of the operator's position: when it began, when the target and stop printed, when it
 * went flat. The one thing the moment needs that no single read carries. */
export interface HeldMemory {
  since: number | null;
  levels: HeldLevels | null;
  targetAt: number | null;
  stopAt: number | null;
  flatAt: number | null;
  flatKey: string | null;
  /** The stop and target `stopAt` / `targetAt` are about: a moved stop (raised, or set) starts its watch again. */
  stopFor?: number | null;
  targetFor?: number | null;
}

export const NO_HELD: HeldMemory = { since: null, levels: null, targetAt: null, stopAt: null, flatAt: null, flatKey: null };

export interface MomentInputs {
  read: StockRead | null;
  /** The desk venue (live | paper | sim), or null when the status names none: on Live a flush is described only. */
  venue: string | null;
  /** The account's position in the stock on the desk's venue; null when none. */
  position: { qty: number; avgCost: number | null } | null;
  /** The live last trade (the read's price when the tab has none). */
  last: number | null;
  now: number;
  /** The venue sleeve's risk per trade: what sizes the operator's own buys. */
  riskUsd: number;
  held: HeldMemory;
  /** Trial T1's 30 s tape reading while you hold (`/flush`); absent or null when unread. */
  flush?: { at: number; score: number | null; label: string } | null;
  /** The big sellers and buyers on the held Level 2 line while you hold (#846); absent or null when unread. */
  big?: BigWalls | null;
}

export type StepIndex = 0 | 1 | 2 | 3 | 4;
export type MomentTone = 'forming' | 'near' | 'go' | 'holding' | 'target' | 'stop' | 'done' | 'wait' | 'thin';
export type CallTone = 'go' | 'target' | 'stop' | 'done' | 'wait' | 'info';
export type ExitLabel = 'Your exit' | 'Your cover';

/** A call's tag on the chart: at its price, on the candle of its moment. */
export interface CallPin {
  label: string;
  price: number;
  /** Epoch seconds of the event; null: the latest candle. */
  at: number | null;
}

export interface MomentCall {
  /** One event: its ping keys on this, once per page. */
  id: string;
  tone: CallTone;
  title: string;
  detail: string;
  pin: CallPin | null;
  ping: boolean;
  /** Every further reason, one a line, shown on hover; absent when the detail says all. */
  more?: string[];
}

export interface Moment {
  /** 0 Forming, 1 Trigger, 2 Holding, 3 the exit; 4 once every step is done. */
  step: StepIndex;
  /** A short's moment (ADR 048): the track reads Forming · Trigger · Short · Your cover. */
  side?: 'short';
  /** The last step: the operator's exit (a short's cover). */
  exitLabel: ExitLabel;
  tone: MomentTone;
  badge: string;
  /** False: the badge alone, for a hand trade with no setup behind it. */
  track: boolean;
  call: MomentCall | null;
}

export const STEP_NAMES = ['Forming', 'Trigger', 'Holding'] as const;

/** The setup a plan follows, as a key: its live id, else its type (a forming setup has no id yet). */
export function planKey(plan: StockPlan | null): string | null {
  if (!plan || plan.source !== 'setup') return null;
  return plan.setup_id ?? plan.setup_type;
}

export function fmtPnl(usd: number | null): string {
  if (usd === null || !Number.isFinite(usd)) return '';
  const cents = Math.round(usd * 100) / 100;
  return `${cents < 0 ? '-' : '+'}$${Math.abs(cents).toFixed(2)}`;
}

function lastOf(i: MomentInputs): number | null {
  return i.last ?? i.read?.price ?? null;
}

/** Shares the account holds long (a short is `shortQty`'s, ADR 048). */
export function heldQty(i: MomentInputs): number {
  return i.position && i.position.qty > 0 ? i.position.qty : 0;
}

/** A triggered setup's levels: what a hand entry at its trigger is judged by. */
function triggeredLevels(plan: StockPlan | null): HeldLevels | null {
  if (!plan || plan.source !== 'setup' || plan.state !== 'triggered') return null;
  return plan.stop !== null && plan.target !== null
    ? { entry: plan.entry, stop: plan.stop, target: plan.target, key: planKey(plan) }
    : null;
}

export interface JudgedLevels {
  entry: number | null;
  stop: number | null;
  target: number | null;
}

/** The stop and target a held position is judged by: the read's view of the position, the operator's own plan,
 * or the triggered setup's the episode began under. */
export function judgedLevels(i: MomentInputs, held: HeldMemory = i.held): JudgedLevels | null {
  // The read's own view of the position (ADR 036 amendment 2026-10-01): your stop (or the one Nova proposes)
  // and target 1 off your average (the target menu's, #845).
  const h = i.read?.held ?? null;
  if (h) return { entry: h.avg, stop: h.stop?.price ?? null, target: h.target?.price ?? null };
  const plan = i.read?.plan ?? null;
  if (plan?.source === 'manual') return { entry: plan.entry, stop: plan.stop, target: plan.target };
  return held.levels ? { entry: held.levels.entry, stop: held.levels.stop, target: held.levels.target } : null;
}

/** The next memory after one more look at the position and the price. */
export function nextHeld(prev: HeldMemory, i: MomentInputs): HeldMemory {
  const plan = i.read?.plan ?? null;
  if (heldQty(i) > 0) {
    let next: HeldMemory = prev.since === null ? { ...NO_HELD, since: i.now } : prev;
    // Only a setup triggered as the shares were bought judges them: one that triggers minutes into a
    // hand trade is not that trade's plan. The window allows for the positions read catching up.
    if (!next.levels && i.now - (next.since ?? i.now) <= ENTER_NOW_SEC) {
      const lv = triggeredLevels(plan);
      if (lv) next = { ...next, levels: lv };
    }
    const lv = judgedLevels(i, next);
    const last = lastOf(i);
    if (lv && (lv.stop ?? null) !== (next.stopFor ?? null)) next = { ...next, stopAt: null, stopFor: lv.stop };
    if (lv && (lv.target ?? null) !== (next.targetFor ?? null)) next = { ...next, targetAt: null, targetFor: lv.target };
    if (last !== null && lv) {
      if (lv.target !== null && next.targetAt === null && last >= lv.target - EPS) next = { ...next, targetAt: i.now };
      if (lv.stop !== null && next.stopAt === null && last <= lv.stop + EPS) next = { ...next, stopAt: i.now };
    }
    return next;
  }
  if (prev.since !== null) return { ...NO_HELD, flatAt: i.now, flatKey: prev.levels?.key ?? null };
  return prev;
}

function pinAt(label: string, price: number | null, at: number | null): CallPin | null {
  return price === null ? null : { label, price, at };
}

function recent(ts: number | null, now: number, within: number): boolean {
  return ts !== null && now - ts >= -1 && now - ts <= within;
}

// -- holding --------------------------------------------------------------------------------
function dueExit(held: HeldMemory): 'target' | 'stop' | null {
  if (held.targetAt === null && held.stopAt === null) return null;
  if (held.stopAt === null) return 'target';
  if (held.targetAt === null) return 'stop';
  return held.stopAt >= held.targetAt ? 'stop' : 'target';
}

function holding(i: MomentInputs, qty: number): Moment {
  const lv = judgedLevels(i);
  const cost = i.position?.avgCost ?? null;
  const last = lastOf(i);
  const pnl = cost !== null && last !== null ? (last - cost) * qty : null;
  const track = lv !== null || i.read?.plan?.source === 'setup';
  const inTrade = `IN THE TRADE${pnl !== null ? ` · ${fmtPnl(pnl)}` : ''}`;
  const due = dueExit(i.held);
  const level = due && lv ? (due === 'target' ? lv.target : lv.stop) : null;
  if (due && level !== null) {
    const word = due === 'target' ? 'TARGET' : 'STOP';
    const at = due === 'target' ? i.held.targetAt : i.held.stopAt;
    const printed = due === 'target'
      ? `${fmtPx(level)} or higher traded at ${hhmmssEt(at)}.`
      : `${fmtPx(level)} or lower printed at ${hhmmssEt(at)}.`;
    const atStop = due === 'stop' && cost !== null && lv?.stop != null
      ? ` At the stop the trade is about ${fmtPnl((lv.stop - cost) * qty)}.`
      : '';
    return {
      step: 3, exitLabel: 'Your exit', tone: due, badge: `${word} ${fmtPx(level)} HIT · SELL`, track,
      call: {
        id: `sell-${due}:${i.held.since ?? 0}:${level}`, tone: due, title: `SELL NOW · ${word} ${fmtPx(level)}`,
        detail: `${printed} No order is working: the exit is yours.${atStop}`, pin: pinAt('SELL NOW', last, at),
        ping: true,
      },
    };
  }
  const said = heldCall(i);
  return { step: 2, exitLabel: 'Your exit', tone: 'holding', badge: said?.badge ?? inTrade, track, call: said?.call ?? null };
}

// -- the setup ----------------------------------------------------------------------------------
function triggerCall(i: MomentInputs, plan: StockPlan, lane: SetupLane | null): MomentCall | null {
  const at = lane?.setup?.triggered_at ?? null;
  if (at === null || !recent(at, i.now, ENTER_NOW_SEC)) return null;
  const key = plan.setup_id ?? `${plan.setup_type}:${at}`;
  const tape = plan.tape?.verdict ?? null;
  if (tape !== 'go') {
    const why = plan.tape?.reasons[0] ? `: ${plan.tape.reasons[0]}` : '';
    return {
      id: `trigger-tape:${key}`, tone: 'wait', title: `TRIGGERED · TAPE ${(tape ?? 'unknown').toUpperCase()}`,
      detail: `The setup triggered, but the tape is not at go${why}. Nova calls no entry.`, pin: null,
      ping: false,
    };
  }
  const last = lastOf(i);
  if (plan.entry === null || plan.risk === null || last === null) return null;
  const away = Math.abs(last - plan.entry);
  if (away > ENTER_NOW_RISK_SHARE * plan.risk + EPS) {
    return {
      id: `trigger-far:${key}`, tone: 'wait', title: 'TRIGGERED · TOO FAR',
      detail: `${fmtPx(last)} is ${fmtStep(away, plan.entry)} from the ${fmtPx(plan.entry)} entry, more than half the `
        + 'risk. Nova calls no entry.',
      pin: null, ping: false,
    };
  }
  const size = sizeFor(i.riskUsd, plan.risk);
  const printed = fmtPx(lane?.setup?.trigger_price ?? plan.trigger);
  const shares = size !== null ? ` ${size.toLocaleString('en-US')} shares risk $${i.riskUsd}.` : '';
  return {
    id: `enter:${key}`, tone: 'go', title: `${enterWord(plan)} · ${fmtPx(plan.entry)}`,
    detail: `${printed} printed with the tape at go.${shares}${actWords(plan)}`, pin: pinAt(enterWord(plan), plan.entry, at),
    ping: true,
  };
}

/** GET READY while the setup is near its trigger; nothing before that. */
function waitingCall(plan: StockPlan, lane: SetupLane | null): MomentCall | null {
  if (plan.state !== 'near') return null;
  const trigger = fmtPx(plan.trigger);
  const near = lane?.distance != null ? `${fmtStep(lane.distance, plan.entry)} ${nearSide(plan)} the trigger. ` : '';
  const [title, detail] = shortWaitingWords(plan, near, trigger)
    ?? ['GET READY', `${near}Enter above ${trigger}: the chart says ENTER NOW when it prints.`];
  return { id: `waiting:${planKey(plan) ?? ''}`, tone: 'info', title, detail, pin: null, ping: false };
}

/** A plan that is not a trade calls no entry: it says so. */
function notTradeCall(plan: StockPlan, why: string): MomentCall {
  return {
    id: `not-a-trade:${planKey(plan) ?? ''}`, tone: 'wait', title: 'NOT A TRADE',
    detail: why.replace(/^Not a trade: /, ''), pin: null, ping: false,
  };
}

function setup(i: MomentInputs, plan: StockPlan): Moment {
  const read = i.read as StockRead;
  const lane = planLane(plan, read.setups);
  const name = `${setupName(plan.setup_type).toUpperCase()}${plan.side === 'short' ? ' ▼ SHORT' : ''}`;
  const exitLabel: ExitLabel = 'Your exit';
  if (thinPlan(plan)) {
    // Too thin to trade (operator decision 2026-10-01): no track, no call to enter, not even its result --
    // nobody could have traded the scored price.
    return { step: 0, exitLabel, tone: 'thin', badge: `${name} · TOO THIN TO TRADE`, track: false, call: null };
  }
  if (plan.result) {
    // It played out: its result, never TRIGGERED again, and no call to enter (operator report, 2026-09-29).
    return { step: 1, exitLabel, tone: plan.result.outcome === 'stop_first' ? 'stop' : 'done',
      badge: `${name} · ${resultBadge(plan.result)}`, track: true, call: null };
  }
  const noTrade = notATrade(plan);
  if (plan.state === 'triggered') {
    if (noTrade) {
      return { step: 1, exitLabel, tone: 'wait', badge: `${name} · TRIGGERED · NOT A TRADE`, track: true,
        call: notTradeCall(plan, noTrade) };
    }
    return { step: 1, exitLabel, tone: 'go', badge: `${name} · TRIGGERED`, track: true, call: triggerCall(i, plan, lane) };
  }
  const state = planBadge(plan, lane).replace(/(\d+)\/(\d+)/, '$1 OF $2');
  if (noTrade) {
    return { step: 0, exitLabel, tone: 'wait', badge: `${name} · ${state} · NOT A TRADE`, track: true,
      call: plan.state === 'near' ? notTradeCall(plan, noTrade) : null };
  }
  return {
    step: 0,
    exitLabel,
    tone: plan.state === 'forming' ? 'forming' : 'near',
    badge: `${name} · ${state}`,
    track: true,
    call: waitingCall(plan, lane),
  };
}

/** Where the trade stands now; null when there is no setup and no position. */
export function momentOf(i: MomentInputs): Moment | null {
  const plan = i.read?.plan ?? null;
  const qty = heldQty(i);
  if (qty > 0) return holding(i, qty);
  const key = planKey(plan);
  if (key !== null && i.held.flatAt !== null && i.held.flatKey === key) {
    return { step: 4, exitLabel: 'Your exit', tone: 'done', badge: 'FLAT · YOU SOLD', track: true, call: null };
  }
  if (!plan || plan.source !== 'setup') return null;
  // A short setup's plan (ADR 049): its track reads Forming · Trigger · Short · Your exit.
  const m = setup(i, plan);
  return plan.side === 'short' ? { ...m, side: 'short' } : m;
}
