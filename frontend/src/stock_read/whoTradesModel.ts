/**
 * Who trades the stock on the desk (ADR 037), pure: the four modes in words, why a side of the switch
 * is locked, the plan card's buttons for the mode, and the plan's levels with what stands behind each
 * -- drawn dashed on the charts while only a plan, solid while an order stands there, and as ENTRY /
 * STOP / TARGET rows in the Level 2 book.
 */
import type { DepthMarker } from '../ibkr';
import { NOT_A_TRADE_NOVA, SETUP_COLORS } from './constants';
import { fmtPnl, heldQty, judgedLevels, type Moment, type MomentInputs } from './momentModel';
import { approveQty } from './novaPromise';
import { fmtPx, fmtStep } from './planMath';
import { thinPlan } from './planVerdict';
import type { StockModeName, StockModeTrade, StockModeView, StockPlan, StockSide } from './types';

export const MODE_NAMES: Record<StockModeName, string> = {
  signal: 'Signal only',
  approve: 'Approve',
  auto_entry: 'Auto-entry',
  bot: 'Bot',
};

export const MODE_SIDES: Record<StockModeName, string> = {
  signal: 'you buy · you sell',
  approve: 'you approve · bot sells',
  auto_entry: 'bot buys · you sell',
  bot: 'bot buys · bot sells',
};

export const MODE_ORDER: readonly StockModeName[] = ['signal', 'approve', 'auto_entry', 'bot'];

/** What the mode means, in the plan card's words. Auto-entry follows the bot's rules with the exit handed
 * to you (ADR 042 draft): a go trigger of a setup at Strategy, while the bot is active, within the day's
 * shared cap. */
export function modeSentence(mode: StockModeName, symbol: string): string {
  switch (mode) {
    case 'approve':
      return 'You approve once. Nova sends the buy with its stop and target.';
    case 'auto_entry':
      return `The bot buys ${symbol} at a go trigger of a setup at Strategy, by the bot's rules, while the bot is `
        + 'on. Every sell is yours.';
    case 'bot':
      return `The bot buys ${symbol} at a go trigger of a setup at Strategy while it is active, and sells at the `
        + 'target, the stop or after 15 minutes.';
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
/** Why Nova does not take the exit of a held stock on Live (the backend's `STOCK_MODE_WHY_LIVE_EXIT`). */
export const HELD_LIVE_EXIT_WHY = 'On Live, Nova never moves a Live order by itself, and a plain IBKR stop does not '
  + 'trigger before 9:30 (#604). Set your stop and sell it yourself; Nova takes the exit on Paper and Sim.';

export function switchLock(
  view: StockModeView | null,
  to: { buy: StockSide; sell: StockSide },
  o: { symbol: string; held: number; pending: string | null },
): string | null {
  if (o.pending) return o.pending;
  if (!view) return `Reading who trades ${o.symbol}…`;
  if (to.buy === 'nova' && view.locks.buy) return view.locks.buy;
  if (to.sell === 'nova' && view.locks.sell) return o.held > 0 ? HELD_LIVE_EXIT_WHY : view.locks.sell;
  // Sell to Nova on a stock you hold opens "Nova takes the exit" (the row's own handler): no lock here.
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
    // Nova's exits: the bracket's two legs are orders from the send (the bot's entry is a bracket too,
    // spec I); a bot trade without a stop order watches its stop. Once the operator takes the exit over,
    // both are only the plan again.
    const nova = live.exits === 'nova';
    const bot = live.kind === 'bot';
    const botStop: Behind = live.stop_order_id !== null ? 'order' : holding ? 'watched' : 'plan';
    return {
      entry: level(live.fill_price ?? live.entry, holding ? 'held' : 'order'),
      stop: level(live.stop, !nova ? 'plan' : bot ? botStop : 'order'),
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
  // A setup plan too thin to trade is no plan (2026-10-01): nothing drawn, nothing marked in Level 2.
  if (!plan || thinPlan(plan)) return null;
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
  /** Why the plan is not a trade (2026-09-29): Approve says it instead of acting; null when it is one. */
  notTrade?: string | null;
  symbol: string;
}

/** Approve's lock for a plan that is not a trade: the reasons, and that Nova's buys are blocked too. */
function notTradeLock(notTrade: string | null | undefined): string | null {
  return notTrade ? `${notTrade} ${NOT_A_TRADE_NOVA}` : null;
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
  // Nova's size for the plan when the view gives one (the sleeve's), else the risk per trade over the risk.
  const size = approveQty(view, a.inputs.riskUsd, plan);
  const noSize = view.size?.text
    ? `Nova sends nothing: ${view.size.text}`
    : plan ? `$${a.inputs.riskUsd} of risk buys no whole share at ${fmtStep(plan.risk, plan.entry)} a share.` : '';
  const sized = view.size ? ' (the size Nova sends for this plan)' : ` ($${a.inputs.riskUsd} risk per trade)`;
  if (plan?.source === 'setup' && plan.state === 'triggered') {
    return {
      id: 'approve-now',
      label: `Approve: buy ${size ?? '?'} now`,
      tone: 'primary',
      locked: notTradeLock(a.notTrade) ?? (plan.setup_id === null ? 'The setup has no live id to approve.'
        : size === null ? noSize : null),
      tip: `Sends buy ${size ?? '?'}${sized} @ ${fmtPx(plan.entry)} now, with its stop ${fmtPx(plan.stop)} and target `
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
    locked: why ?? notTradeLock(a.notTrade),
    tip: plan ? `At the trigger, with the tape at go, Nova sends buy ${size ?? '?'}${sized} @ ${fmtPx(plan.entry)} `
      + `with stop ${fmtPx(plan.stop)} and target ${fmtPx(plan.target)}. Withdrawn if the setup re-arms, fails or `
      + 'disarms.'
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
  // A take-over always leaves Buy on You (ADR 042 draft): it never turns the stock into Auto-entry.
  const buyStays = `Buy stays on You: the bot buys no more ${a.symbol}.`;
  if (qty > 0) {
    if (live?.exits === 'nova') {
      const approve = live.kind === 'approve';
      return {
        actions: [{
          id: 'take-over',
          label: approve ? 'Cancel stop and target' : 'Take over the exit',
          tone: 'plain',
          locked: live.exiting ? 'The bot is already selling.' : null,
          tip: approve
            ? `Nova cancels the bracket's stop and target at the broker, and the exit is yours. ${buyStays}`
            : `Nova cancels the bot's target and stop on ${a.symbol} and stops its 15-minute clock, and the exit is `
              + `yours. The stock leaves the bot's list (Signal only): ${buyStays}`,
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
      tip: `Nova cancels the bot's buy that has not filled, with its stop and target. The stock leaves the bot's `
        + `list (Signal only): ${buyStays}` }], status: null };
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
