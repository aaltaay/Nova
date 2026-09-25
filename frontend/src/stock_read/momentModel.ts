/**
 * The trade's moment on the 1-minute chart (ADR 037), pure: where the setup and the position stand --
 * the badge and its track (Forming, Trigger, Holding, then the exit) -- and the call in the chart's
 * corner: ENTER NOW, SELL NOW, or what Nova just did, with the id its one ping keys on. Every price is
 * the read's, the view's or the position's own; nothing is estimated.
 *
 * maintainer: one-concern the moment ladder and its calls must be judged in one place, so the badge, the
 * track, the call and its ping can never disagree about where the trade stands.
 */
import { ENTER_NOW_RISK_SHARE, ENTER_NOW_SEC, NOVA_CALL_SEC, STOCK_MODE_ENTRY_TTL_SEC } from './constants';
import { fmtPx, fmtStep, planBadge, planLane, setupName, sizeFor } from './planMath';
import { hhmmssEt } from './timeWords';
import type { SetupLane, StockModeName, StockModeTrade, StockModeView, StockPlan, StockRead } from './types';

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
}

export const NO_HELD: HeldMemory = { since: null, levels: null, targetAt: null, stopAt: null, flatAt: null, flatKey: null };

export interface MomentInputs {
  read: StockRead | null;
  who: StockModeView | null;
  /** The account's position in the stock on the desk's venue; null when none. */
  position: { qty: number; avgCost: number | null } | null;
  /** The live last trade (the read's price when the tab has none). */
  last: number | null;
  now: number;
  riskUsd: number;
  held: HeldMemory;
}

export type StepIndex = 0 | 1 | 2 | 3 | 4;
export type MomentTone = 'forming' | 'near' | 'go' | 'holding' | 'target' | 'stop' | 'done' | 'wait';
export type CallTone = 'go' | 'target' | 'stop' | 'nova' | 'done' | 'wait' | 'info';
export type ExitLabel = 'Your exit' | 'Target / stop';

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
}

export interface Moment {
  /** 0 Forming, 1 Trigger, 2 Holding, 3 the exit; 4 once every step is done. */
  step: StepIndex;
  /** The last step: the operator's exit, or the orders Nova holds. */
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

function liveTrade(who: StockModeView | null): StockModeTrade | null {
  const t = who?.trade ?? null;
  return t && (t.state === 'entering' || t.state === 'holding') ? t : null;
}

/** Shares held: the account's, or Nova's filled trade while the positions read catches up. */
export function heldQty(i: MomentInputs): number {
  const live = liveTrade(i.who);
  const own = i.position && i.position.qty > 0 ? i.position.qty : 0;
  const nova = live?.state === 'holding' && live.qty !== null ? live.qty : 0;
  return Math.max(own, nova);
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

/** The stop and target a held position is judged by: Nova's live trade's own, the operator's own plan, or
 * the triggered setup's the episode began under. */
export function judgedLevels(i: MomentInputs, held: HeldMemory = i.held): JudgedLevels | null {
  const live = liveTrade(i.who);
  if (live) return { entry: live.fill_price ?? live.entry, stop: live.stop, target: live.target };
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

function recent(ts: number | null, now: number, within = NOVA_CALL_SEC): boolean {
  return ts !== null && now - ts >= -1 && now - ts <= within;
}

function modeOf(i: MomentInputs): StockModeName {
  return i.who?.mode ?? 'signal';
}

function novaHoldsExits(mode: StockModeName): ExitLabel {
  return mode === 'approve' || mode === 'bot' ? 'Target / stop' : 'Your exit';
}

// -- Nova's orders ------------------------------------------------------------------------
function entering(t: StockModeTrade): Moment {
  const size = `${t.qty ?? '?'} @ ${fmtPx(t.entry)}`;
  const words: Record<StockModeTrade['kind'], { badge: string; detail: string }> = {
    auto_entry: {
      badge: `NOVA BUYING · ${size}`,
      detail: `Nova sent the buy at ${hhmmssEt(t.sent_at)}. Unfilled after ${STOCK_MODE_ENTRY_TTL_SEC} s it is `
        + 'cancelled. Every sell is yours.',
    },
    approve: {
      badge: `SENT · BUY ${size}`,
      detail: `The buy went with its stop ${fmtPx(t.stop)} and target ${fmtPx(t.target)}. Unfilled after `
        + `${STOCK_MODE_ENTRY_TTL_SEC} s, all three are cancelled.`,
    },
    bot: {
      badge: `BOT BUYING · ${size}`,
      detail: `The bot sent its buy. It sells at ${fmtPx(t.target)}, at ${fmtPx(t.stop)} or after 15 minutes.`,
    },
  };
  const w = words[t.kind];
  return {
    step: 1,
    exitLabel: t.exits === 'nova' ? 'Target / stop' : 'Your exit',
    tone: 'go',
    badge: w.badge,
    track: true,
    call: {
      id: `sent:${t.entry_order_id ?? t.sent_at}`, tone: 'nova', title: w.badge, detail: w.detail,
      pin: pinAt(t.kind === 'approve' ? 'SENT' : 'NOVA BUYING', t.entry, t.sent_at), ping: false,
    },
  };
}

function boughtCall(i: MomentInputs, t: StockModeTrade | null): MomentCall | null {
  if (!t || t.state !== 'holding' || !recent(t.filled_at, i.now)) return null;
  const fill = `${t.qty ?? '?'} @ ${fmtPx(t.fill_price)}`;
  const words: Record<StockModeTrade['kind'], [string, string, string]> = {
    auto_entry: [`NOVA BOUGHT ${fill}`, 'NOVA BOUGHT', 'No stop or target is working. The exit is yours.'],
    approve: [`BOUGHT ${fill}`, 'BOUGHT', `The stop ${fmtPx(t.stop)} and the target ${fmtPx(t.target)} are working at `
      + 'the broker. The first one hit cancels the other.'],
    bot: [`NOVA BOUGHT ${fill}`, 'NOVA BOUGHT', `Target ${fmtPx(t.target)} resting. Nova watches the `
      + `${fmtPx(t.stop)} stop and sells after 15 minutes.`],
  };
  const [title, pill, detail] = words[t.kind];
  return {
    id: `bought:${t.entry_order_id ?? t.filled_at}`, tone: 'nova', title, detail,
    pin: pinAt(pill, t.fill_price, t.filled_at), ping: true,
  };
}

// -- holding --------------------------------------------------------------------------------
function dueExit(held: HeldMemory): 'target' | 'stop' | null {
  if (held.targetAt === null && held.stopAt === null) return null;
  if (held.stopAt === null) return 'target';
  if (held.targetAt === null) return 'stop';
  return held.stopAt >= held.targetAt ? 'stop' : 'target';
}

function holding(i: MomentInputs, live: StockModeTrade | null, qty: number): Moment {
  const lv = judgedLevels(i);
  const cost = i.position?.avgCost ?? live?.fill_price ?? null;
  const last = lastOf(i);
  const pnl = cost !== null && last !== null ? (last - cost) * qty : null;
  const track = live !== null || lv !== null || i.read?.plan?.source === 'setup';
  const inTrade = `IN THE TRADE${pnl !== null ? ` · ${fmtPnl(pnl)}` : ''}`;
  if (live?.exits === 'nova') {
    if (live.exiting) {
      return {
        step: 3, exitLabel: 'Target / stop', tone: 'target', badge: 'NOVA IS SELLING', track,
        call: {
          id: `exiting:${live.setup_id ?? live.entry_order_id}`, tone: 'nova', title: 'NOVA IS SELLING',
          detail: 'The bot is selling: its target, its stop or its 15 minutes came.', pin: null,
          ping: false,
        },
      };
    }
    return { step: 2, exitLabel: 'Target / stop', tone: 'holding', badge: inTrade, track, call: boughtCall(i, live) };
  }
  const due = dueExit(i.held);
  const level = due && lv ? (due === 'target' ? lv.target : lv.stop) : null;
  if (due && level !== null) {
    const word = due === 'target' ? 'TARGET' : 'STOP';
    const at = due === 'target' ? i.held.targetAt : i.held.stopAt;
    const nobody = live?.kind === 'auto_entry' || modeOf(i) === 'auto_entry'
      ? 'Nova will not sell: the exit is yours.'
      : 'No order is working: the exit is yours.';
    const printed = due === 'target'
      ? `${fmtPx(level)} or higher traded at ${hhmmssEt(at)}.`
      : `${fmtPx(level)} or lower printed at ${hhmmssEt(at)}.`;
    const atStop = due === 'stop' && cost !== null && lv?.stop != null
      ? ` At the stop the trade is about ${fmtPnl((lv.stop - cost) * qty)}.`
      : '';
    return {
      step: 3, exitLabel: 'Your exit', tone: due, badge: `${word} ${fmtPx(level)} HIT · SELL`, track,
      call: {
        id: `sell-${due}:${i.held.since ?? live?.filled_at ?? 0}`, tone: due, title: `SELL NOW · ${word} ${fmtPx(level)}`,
        detail: `${printed} ${nobody}${atStop}`, pin: pinAt('SELL NOW', last, at), ping: true,
      },
    };
  }
  return { step: 2, exitLabel: 'Your exit', tone: 'holding', badge: inTrade, track, call: boughtCall(i, live) };
}

// -- after Nova's trade -----------------------------------------------------------------------
/** Nova's trade that ended on the plan's own setup (or so recently its call still shows). */
function finishedTrade(i: MomentInputs): StockModeTrade | null {
  const t = i.who?.trade ?? null;
  if (!t || (t.state !== 'closed' && t.state !== 'missed')) return null;
  const plan = i.read?.plan ?? null;
  const same = t.setup_id !== null && t.setup_id === plan?.setup_id;
  if (t.state === 'missed') return recent(t.closed_at, i.now) ? t : null;
  return same || recent(t.closed_at, i.now) ? t : null;
}

function finished(i: MomentInputs, t: StockModeTrade): Moment {
  const pnl = t.exit_price !== null && t.fill_price !== null && t.qty !== null
    ? (t.exit_price - t.fill_price) * t.qty
    : null;
  if (t.state === 'missed') {
    const again = t.kind === 'auto_entry' ? ' A miss gives the day\'s entry back: Nova buys at the next trigger.' : '';
    return {
      step: 1, exitLabel: t.exits === 'nova' ? 'Target / stop' : 'Your exit', tone: 'wait', badge: 'NOVA\'S BUY MISSED',
      track: true,
      call: {
        id: `missed:${t.entry_order_id ?? t.sent_at}`, tone: 'wait', title: 'NOVA\'S BUY MISSED',
        detail: `${t.qty ?? '?'} @ ${fmtPx(t.entry)} did not fill in ${STOCK_MODE_ENTRY_TTL_SEC} s and was cancelled.${again}`,
        pin: null, ping: false,
      },
    };
  }
  const money = pnl !== null ? ` · ${fmtPnl(pnl)}` : '';
  const exit = fmtPx(t.exit_price);
  const said: Record<string, [string, string]> = {
    target: [`SOLD ${exit}${money}`, t.kind === 'bot' ? 'The bot\'s target filled.' : 'The target filled at the broker; '
      + 'the stop was cancelled.'],
    stop: [`STOPPED ${exit}${money}`, t.kind === 'bot' ? 'The bot sold at its stop.' : 'The stop filled at the broker; '
      + 'the target was cancelled.'],
    time: [`TIME STOP ${exit}${money}`, 'The bot sold after 15 minutes in the trade.'],
    flush: [`SOLD ${exit}${money}`, 'The bot sold on a flush of the tape.'],
  };
  const [badge, detail] = said[t.exit_reason ?? ''] ?? [`FLAT${money}`, 'The position was closed outside Nova\'s orders.'];
  const fresh = recent(t.closed_at, i.now);
  return {
    step: fresh ? 3 : 4,
    exitLabel: t.exits === 'nova' ? 'Target / stop' : 'Your exit',
    tone: t.exit_reason === 'stop' ? 'stop' : 'done',
    badge: fresh ? badge : `FLAT${money}`,
    track: true,
    call: fresh ? {
      id: `closed:${t.setup_id ?? t.entry_order_id}:${t.closed_at}`, tone: t.exit_reason === 'stop' ? 'stop' : 'done',
      title: badge, detail, pin: t.exit_reason === 'target' ? pinAt(`SOLD ${exit}`, t.exit_price, t.closed_at) : null,
      ping: t.exit_reason === 'target' || t.exit_reason === 'stop' || t.exit_reason === 'time',
    } : null,
  };
}

// -- the setup ----------------------------------------------------------------------------------
function eventCall(i: MomentInputs, since: number | null): MomentCall | null {
  const e = i.who?.last_event ?? null;
  if (!e || !recent(e.ts, i.now) || (since !== null && e.ts < since - 1)) return null;
  const tone: CallTone = e.tone === 'bad' ? 'stop' : e.tone === 'warn' ? 'wait' : e.tone === 'ok' ? 'done' : 'info';
  return { id: `event:${e.ts}`, tone, title: 'NOVA', detail: e.text, pin: null, ping: false };
}

function triggerCall(i: MomentInputs, plan: StockPlan, lane: SetupLane | null, mode: StockModeName): MomentCall | null {
  const at = lane?.setup?.triggered_at ?? null;
  if (at === null || !recent(at, i.now, ENTER_NOW_SEC)) return eventCall(i, at);
  const key = plan.setup_id ?? `${plan.setup_type}:${at}`;
  const approval = i.who?.approval ?? null;
  if (mode === 'auto_entry' || mode === 'bot' || (mode === 'approve' && approval?.state === 'waiting')) {
    // Nova decides at this trigger: its own words say what it did.
    return eventCall(i, at) ?? (mode === 'bot' && i.who?.bot && !i.who.bot.playing
      ? { id: `bot-idle:${key}`, tone: 'wait', title: 'THE BOT IS NOT TRADING IT', detail: i.who.bot.reason ?? '',
        pin: null, ping: false }
      : null);
  }
  if (mode === 'approve' && approval?.state === 'withdrawn') {
    return { id: `withdrawn:${approval.approved_at}`, tone: 'wait', title: 'NOT SENT', detail: approval.reason ?? '',
      pin: null, ping: false };
  }
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
  const act = mode === 'approve' ? ` Approve: buy ${size ?? '?'} now sends it with its stop and target.` : ' Your click.';
  return {
    id: `enter:${key}`, tone: 'go', title: `ENTER NOW · ${fmtPx(plan.entry)}`,
    detail: `${printed} printed with the tape at go.${shares}${act}`, pin: pinAt('ENTER NOW', plan.entry, at),
    ping: true,
  };
}

function waitingCall(i: MomentInputs, plan: StockPlan, lane: SetupLane | null, mode: StockModeName): MomentCall | null {
  const key = planKey(plan) ?? '';
  const approval = i.who?.approval ?? null;
  if (mode === 'approve' && approval?.state === 'waiting') {
    return {
      id: `approved:${approval.setup_id}`, tone: 'nova', title: 'APPROVED',
      detail: `Nova sends buy ${approval.qty} @ ${fmtPx(approval.entry)} with stop ${fmtPx(approval.stop)} and target `
        + `${fmtPx(approval.target)} when ${fmtPx(plan.trigger)} prints with the tape at go.`,
      pin: null, ping: false,
    };
  }
  if (mode === 'approve' && approval?.state === 'withdrawn') {
    return { id: `withdrawn:${approval.approved_at}`, tone: 'wait', title: 'APPROVAL WITHDRAWN',
      detail: approval.reason ?? '', pin: null, ping: false };
  }
  if (plan.state === 'forming') return eventCall(i, null);
  const size = sizeFor(i.riskUsd, plan.risk);
  const trigger = fmtPx(plan.trigger);
  const near = plan.state === 'near' && lane?.distance != null ? `${fmtStep(lane.distance, plan.entry)} under the trigger. ` : '';
  const words: Record<StockModeName, [string, string]> = {
    signal: ['GET READY', `${near}Enter above ${trigger}: the chart says ENTER NOW when it prints.`],
    approve: ['APPROVE TO SEND', `Approve the plan and Nova sends buy ${size ?? '?'} @ ${fmtPx(plan.entry)} with its `
      + 'stop and target at the trigger.'],
    auto_entry: [`NOVA BUYS AT ${trigger}`, `${near}If ${trigger} prints with the tape at go, Nova buys `
      + `${size ?? '?'}. Every sell is yours.`],
    bot: ['THE BOT TRADES THIS', i.who?.bot && !i.who.bot.playing
      ? `The bot will not trade it yet: ${i.who.bot.reason ?? 'it is not playing'}.`
      : `It buys at the trigger and sells at ${fmtPx(plan.target)}, at ${fmtPx(plan.stop)} or after 15 minutes.`],
  };
  if (mode === 'signal' && plan.state !== 'near') return eventCall(i, null);
  const [title, detail] = words[mode];
  return { id: `waiting:${mode}:${key}`, tone: 'info', title, detail, pin: null, ping: false };
}

function setup(i: MomentInputs, plan: StockPlan): Moment {
  const read = i.read as StockRead;
  const lane = planLane(plan, read.setups);
  const mode = modeOf(i);
  const name = setupName(plan.setup_type).toUpperCase();
  const exitLabel = novaHoldsExits(mode);
  if (plan.state === 'triggered') {
    return { step: 1, exitLabel, tone: 'go', badge: `${name} · TRIGGERED`, track: true, call: triggerCall(i, plan, lane, mode) };
  }
  const state = planBadge(plan, lane).replace(/(\d+)\/(\d+)/, '$1 OF $2');
  return {
    step: 0,
    exitLabel,
    tone: plan.state === 'forming' ? 'forming' : 'near',
    badge: `${name} · ${state}`,
    track: true,
    call: waitingCall(i, plan, lane, mode),
  };
}

/** Where the trade stands now; null when there is no setup, no position and nothing Nova did. */
export function momentOf(i: MomentInputs): Moment | null {
  const plan = i.read?.plan ?? null;
  const live = liveTrade(i.who);
  if (live?.state === 'entering') return entering(live);
  const qty = heldQty(i);
  if (qty > 0) return holding(i, live, qty);
  const done = finishedTrade(i);
  if (done) return finished(i, done);
  const key = planKey(plan);
  if (key !== null && i.held.flatAt !== null && i.held.flatKey === key) {
    return { step: 4, exitLabel: novaHoldsExits(modeOf(i)), tone: 'done', badge: 'FLAT · YOU SOLD', track: true, call: null };
  }
  if (!plan || plan.source !== 'setup') return null;
  return setup(i, plan);
}
