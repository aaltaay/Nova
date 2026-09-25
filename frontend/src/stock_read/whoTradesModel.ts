/**
 * Who trades the stock on the desk (ADR 037), pure: the four modes in words, why a side of the switch
 * is locked, the plan card's buttons for the mode, and the plan's levels with what stands behind each
 * -- drawn dashed on the charts while only a plan, solid while an order stands there, and as ENTRY /
 * STOP / TARGET rows in the Level 2 book.
 */
import type { DepthMarker } from '../ibkr';
import { SETUP_COLORS } from './constants';
import { fmtPnl, heldQty, judgedLevels, type Moment, type MomentInputs } from './momentModel';
import { fmtPx, fmtStep, sizeFor } from './planMath';
import type { StockModeName, StockModeTrade, StockModeView, StockPlan, StockSide } from './types';

export const MODE_NAMES: Record<StockModeName, string> = {
  signal: 'Signal only',
  approve: 'Approve',
  auto_entry: 'Auto-entry',
  bot: 'Bot at Strategy',
};

export const MODE_SIDES: Record<StockModeName, string> = {
  signal: 'you buy · you sell',
  approve: 'you approve · Nova sells',
  auto_entry: 'Nova buys · you sell',
  bot: 'Nova buys · Nova sells',
};

export const MODE_ORDER: readonly StockModeName[] = ['signal', 'approve', 'auto_entry', 'bot'];

/** What the mode means, in the plan card's words. */
export function modeSentence(mode: StockModeName, symbol: string): string {
  switch (mode) {
    case 'approve':
      return 'You approve once. Nova sends the buy with its stop and target.';
    case 'auto_entry':
      return `Nova buys ${symbol} once, at the trigger. Every sell is yours.`;
    case 'bot':
      return 'Nova buys at the trigger and sells at the target, the stop or 15 minutes.';
    default:
      return 'Nova draws the plan and tells you when. It places nothing.';
  }
}

export function sidesOf(mode: StockModeName): { buy: StockSide; sell: StockSide } {
  return {
    buy: mode === 'auto_entry' || mode === 'bot' ? 'nova' : 'you',
    sell: mode === 'approve' || mode === 'bot' ? 'nova' : 'you',
  };
}

export function modeOf(buy: StockSide, sell: StockSide): StockModeName {
  if (buy === 'nova') return sell === 'nova' ? 'bot' : 'auto_entry';
  return sell === 'nova' ? 'approve' : 'signal';
}

/** Why the switch cannot move to `to` now; null: it can. `pending` is the desk's own reason to wait. */
export function switchLock(
  view: StockModeView | null,
  to: { buy: StockSide; sell: StockSide },
  o: { symbol: string; held: number; pending: string | null },
): string | null {
  if (o.pending) return o.pending;
  if (!view) return `Reading who trades ${o.symbol}…`;
  if (to.buy === 'nova' && view.locks.buy) return view.locks.buy;
  if (to.sell === 'nova' && view.locks.sell) return view.locks.sell;
  if (to.sell === 'nova' && view.sell === 'you' && o.held > 0) {
    return `You hold ${o.symbol}: Nova exits only a trade it entered or you approved. Keep Sell on You.`;
  }
  return null;
}

// -- the plan's levels and what stands behind them ------------------------------------------------
export type Behind = 'plan' | 'order' | 'held' | 'watched';

export interface OrderLevel {
  price: number;
  behind: Behind;
}

export interface OrderLevels {
  entry: OrderLevel | null;
  stop: OrderLevel | null;
  target: OrderLevel | null;
}

function level(price: number | null, behind: Behind): OrderLevel | null {
  return price !== null && Number.isFinite(price) ? { price, behind } : null;
}

function liveTrade(who: StockModeView | null): StockModeTrade | null {
  const t = who?.trade ?? null;
  return t && (t.state === 'entering' || t.state === 'holding') ? t : null;
}

/** The levels the charts and Level 2 draw: Nova's live trade's own, the levels a held position is judged
 * by, else the plan's. */
export function orderLevels(i: MomentInputs): OrderLevels | null {
  const live = liveTrade(i.who);
  if (live) {
    const holding = live.state === 'holding';
    // Nova's exits: the bracket's two legs are orders from the send; the bot rests its target after the
    // fill and watches its stop. Once the operator takes the exit over, both are only the plan again.
    const nova = live.exits === 'nova';
    const bot = live.kind === 'bot';
    return {
      entry: level(live.fill_price ?? live.entry, holding ? 'held' : 'order'),
      stop: level(live.stop, !nova ? 'plan' : bot ? (holding ? 'watched' : 'plan') : 'order'),
      target: level(live.target, !nova ? 'plan' : bot ? (live.target_order_id !== null ? 'order' : 'plan') : 'order'),
    };
  }
  const plan = i.read?.plan ?? null;
  if (heldQty(i) > 0) {
    // The chart draws the position's own cost; the plan's entry turns solid once shares are held.
    const lv = judgedLevels(i);
    return {
      entry: level(lv?.entry ?? null, 'held'),
      stop: level(lv?.stop ?? null, 'plan'),
      target: level(lv?.target ?? null, 'plan'),
    };
  }
  if (!plan) return null;
  return { entry: level(plan.entry, 'plan'), stop: level(plan.stop, 'plan'), target: level(plan.target, 'plan') };
}

const TIPS: Record<'entry' | 'stop' | 'target', Partial<Record<Behind, string>>> = {
  entry: {
    plan: "The plan's entry, a buy limit here. Only a plan: no order stands behind it.",
    order: "Nova's buy is working here.",
    held: "Shares are held: the plan's entry is in effect.",
  },
  stop: {
    plan: "The plan's stop. Only a plan: no order stands behind it.",
    order: 'A stop order stands here.',
    watched: 'The bot watches this stop and sells when it prints.',
  },
  target: {
    plan: "The plan's target. Only a plan: no order stands behind it.",
    order: 'A sell limit rests here.',
  },
};

/** ENTRY / STOP / TARGET for the Level 2 book. */
export function level2Markers(levels: OrderLevels | null): DepthMarker[] {
  if (!levels) return [];
  const out: DepthMarker[] = [];
  const add = (id: 'entry' | 'stop' | 'target', lv: OrderLevel | null, color: string, rests: 'bid' | 'ask') => {
    if (!lv) return;
    out.push({
      id,
      price: lv.price,
      label: `${id.toUpperCase()} ${fmtPx(lv.price)}`,
      color,
      working: lv.behind !== 'plan',
      rests,
      tip: TIPS[id][lv.behind] ?? '',
    });
  };
  add('entry', levels.entry, SETUP_COLORS.trigger, 'bid');
  add('stop', levels.stop, SETUP_COLORS.stop, 'bid');
  add('target', levels.target, SETUP_COLORS.target, 'ask');
  return out;
}

/** A price line's title for the level and what stands behind it. */
export function levelTitle(id: 'entry' | 'stop' | 'target', behind: Behind, targetR = ''): string {
  if (id === 'entry') return behind === 'held' ? 'ENTRY · held' : behind === 'order' ? 'ENTRY · working' : 'ENTRY';
  if (id === 'stop') return behind === 'order' ? 'STOP · order' : behind === 'watched' ? 'STOP · Nova watches' : 'STOP · plan';
  return behind === 'order' ? 'TARGET · order' : `TARGET${targetR} · plan`;
}

// -- the plan card's buttons -------------------------------------------------------------------------
export type PlanActionId =
  | 'stage'
  | 'stage-sell'
  | 'approve'
  | 'approve-now'
  | 'cancel-approval'
  | 'take-over'
  | 'auto-off'
  | 'bot-off';

export interface PlanAction {
  id: PlanActionId;
  label: string;
  tone: 'primary' | 'plain' | 'target' | 'stop';
  /** Why it cannot act now (`data-why`); null: it can. */
  locked: string | null;
  tip: string;
  /** Stage sell: the shares and the limit. */
  sell?: { qty: number; price: number };
}

export interface PlanActionsInput {
  moment: Moment | null;
  inputs: MomentInputs;
  bid: number | null;
  /** A ticket in this tab takes prefills. */
  listening: boolean;
  /** Stage in ticket's own lock (the plan's entry, stop and size). */
  stageLocked: string | null;
  symbol: string;
}

const NO_TICKET = 'This tab has no order ticket open to fill. Show the Order Entry module on the rail.';

function stageSell(a: PlanActionsInput, qty: number): PlanAction {
  const due = a.moment?.tone === 'target' || a.moment?.tone === 'stop' ? a.moment.tone : null;
  const lv = judgedLevels(a.inputs);
  // An exit that is due sells at the bid; before it, the plan's target is the resting sell.
  const price = due ? (a.bid ?? a.inputs.last) : (lv?.target ?? a.bid ?? a.inputs.last);
  const locked = price === null ? `No bid on ${a.symbol} to sell at yet.` : a.listening ? null : NO_TICKET;
  return {
    id: 'stage-sell',
    label: price === null ? `Stage sell ${qty}` : `Stage sell ${qty} @ ${fmtPx(price)}`,
    tone: due ?? 'plain',
    locked,
    tip: due ? 'Fills the ticket with a sell at the bid. Nothing is sent until you send it.'
      : 'Fills the ticket with a sell at the target. Nothing is sent until you send it.',
    sell: price === null ? undefined : { qty, price },
  };
}

function approveAction(a: PlanActionsInput, plan: StockPlan | null, view: StockModeView): PlanAction {
  const approval = view.approval;
  if (approval?.state === 'waiting') {
    return { id: 'cancel-approval', label: 'Approved · cancel', tone: 'plain', locked: null,
      tip: 'Withdraws the approval. Nova sends nothing at the trigger.' };
  }
  const size = plan ? sizeFor(a.inputs.riskUsd, plan.risk) : null;
  const noSize = plan ? `$${a.inputs.riskUsd} of risk buys no whole share at ${fmtStep(plan.risk, plan.entry)} a share.` : '';
  if (plan?.source === 'setup' && plan.state === 'triggered') {
    return {
      id: 'approve-now',
      label: `Approve: buy ${size ?? '?'} now`,
      tone: 'primary',
      locked: plan.setup_id === null ? 'The setup has no live id to approve.' : size === null ? noSize : null,
      tip: `Sends buy ${size ?? '?'} @ ${fmtPx(plan.entry)} now, with its stop ${fmtPx(plan.stop)} and target `
        + `${fmtPx(plan.target)} at the broker.`,
    };
  }
  const why = !plan || plan.source !== 'setup'
    ? `Approve follows a setup, and none is armed on ${a.symbol}.`
    : plan.state === 'forming' || plan.setup_id === null
      ? 'Nothing to approve yet: the setup has not armed, so its levels are provisional.'
      : size === null ? noSize : null;
  return {
    id: 'approve',
    label: size !== null && plan ? `Approve ${size} @ ${fmtPx(plan.entry)}` : 'Approve',
    tone: 'primary',
    locked: why,
    tip: plan ? `At the trigger, with the tape at go, Nova sends buy ${size ?? '?'} @ ${fmtPx(plan.entry)} with stop `
      + `${fmtPx(plan.stop)} and target ${fmtPx(plan.target)}. Withdrawn if the setup re-arms, fails or disarms.`
      : 'Approve the plan once; Nova sends it at the trigger.',
  };
}

/** The plan card's buttons for the mode and the moment, and the line that says a trade is done. */
export function planActions(a: PlanActionsInput): { actions: PlanAction[]; status: string | null } {
  const view = a.inputs.who;
  const plan = a.inputs.read?.plan ?? null;
  const mode = view?.mode ?? 'signal';
  const qty = heldQty(a.inputs);
  const live = liveTrade(view);
  const stage: PlanAction = {
    id: 'stage', label: 'Stage in ticket', tone: 'primary', locked: a.stageLocked,
    tip: 'Fills this tab\'s ticket with a buy limit at the entry for your size. It never sends.',
  };
  if (qty > 0) {
    if (live?.exits === 'nova') {
      const approve = live.kind === 'approve';
      return {
        actions: [{
          id: 'take-over',
          label: approve ? 'Cancel stop and target' : 'Take over the exit',
          tone: 'plain',
          locked: live.exiting ? 'The bot is already selling.' : null,
          tip: approve ? "Cancels the bracket's stop and target at the broker. The exit becomes yours."
            : 'The bot cancels its target and stops watching its stop. The exit becomes yours.',
        }],
        status: null,
      };
    }
    return { actions: [stageSell(a, qty)], status: null };
  }
  if (live?.state === 'entering') {
    if (live.kind === 'approve') {
      return { actions: [{ id: 'cancel-approval', label: 'Cancel the buy', tone: 'plain', locked: null,
        tip: 'Cancels the buy that has not filled; its stop and target go with it.' }], status: null };
    }
    if (live.kind === 'auto_entry') {
      return { actions: [{ id: 'auto-off', label: 'Auto-entry on · turn off', tone: 'plain', locked: null,
        tip: 'Buy goes back to You and cancels the buy that has not filled.' }], status: null };
    }
    return { actions: [{ id: 'take-over', label: 'Take over', tone: 'plain', locked: null,
      tip: 'The bot cancels its buy that has not filled.' }], status: null };
  }
  const done = view?.trade && view.trade.state === 'closed' && view.trade.setup_id !== null
    && view.trade.setup_id === plan?.setup_id ? view.trade : null;
  const status = done ? `Closed${closedMoney(done)}` : null;
  if (!view) return { actions: [stage], status };
  switch (mode) {
    case 'approve':
      return { actions: done ? [] : [approveAction(a, plan, view)], status };
    case 'auto_entry':
      return {
        actions: [{ id: 'auto-off', label: 'Auto-entry on · turn off', tone: 'plain', locked: null,
          tip: 'Buy goes back to You: Nova will not buy this stock.' }],
        status,
      };
    case 'bot':
      return {
        actions: [{ id: 'bot-off', label: `Bot on ${a.symbol} · stop it`, tone: 'plain', locked: null,
          tip: `Takes ${a.symbol} off the bot's list: back to Signal only.` }],
        status,
      };
    default:
      return { actions: [stage], status };
  }
}

function closedMoney(t: StockModeTrade): string {
  if (t.exit_price === null || t.fill_price === null || t.qty === null) return '';
  return ` · ${fmtPnl((t.exit_price - t.fill_price) * t.qty)}`;
}
