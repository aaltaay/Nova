/**
 * The plan card's buttons for who trades the stock (ADR 037), pure: Stage in ticket (a short plan's "Stage short
 * in ticket", ADR 048), Stage sell, Approve and Approve now, cancelling an approval, taking over the exit, turning
 * Auto-entry or the bot off -- each with why it cannot act now -- and the line that says a trade is done. A short
 * plan is approved as a long one is (#778 step 5): Nova sends the short with its buy stop and cover.
 */
import { NOT_A_TRADE_NOVA } from './constants';
import { fmtPnl, heldQty, judgedLevels, type Moment, type MomentInputs } from './momentModel';
import { approveQty } from './novaPromise';
import { fmtPx, fmtStep } from './planMath';
import type { StockModeTrade, StockModeView, StockPlan } from './types';
import { liveTrade } from './whoTradesModel';

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
  // A short plan is approved like a long one (#778 step 5): its buy stop over the entry, its cover under it.
  const short = plan?.side === 'short';
  const verb = short ? 'short' : 'buy';
  const legs = (p: StockPlan) => (short
    ? `its buy stop ${fmtPx(p.stop)} and cover ${fmtPx(p.target)}` : `its stop ${fmtPx(p.stop)} and target ${fmtPx(p.target)}`);
  const ssr = short ? ' Under SSR it sells at the ask, never under the plan.' : '';
  const noSize = view.size?.text
    ? `Nova sends nothing: ${view.size.text}`
    : plan ? `$${a.inputs.riskUsd} of risk ${verb}s no whole share at ${fmtStep(plan.risk, plan.entry)} a share.` : '';
  const sized = view.size ? ' (the size Nova sends for this plan)' : ` ($${a.inputs.riskUsd} risk per trade)`;
  if (plan?.source === 'setup' && plan.state === 'triggered') {
    return {
      id: 'approve-now',
      label: `Approve: ${verb} ${size ?? '?'} now`,
      tone: 'primary',
      locked: notTradeLock(a.notTrade) ?? (plan.setup_id === null ? 'The setup has no live id to approve.'
        : size === null ? noSize : null),
      tip: `Sends ${verb} ${size ?? '?'}${sized} @ ${fmtPx(plan.entry)} now, with ${legs(plan)} at the broker.${ssr}`,
    };
  }
  const why = !plan || plan.source !== 'setup'
    ? `Approve follows a setup, and none is armed on ${a.symbol}.`
    : plan.state === 'forming' || plan.setup_id === null
      ? 'Nothing to approve yet: the setup has not armed, so its levels are provisional.'
      : size === null ? noSize : null;
  return {
    id: 'approve',
    label: size !== null && plan ? `Approve ${short ? 'short ' : ''}${size} @ ${fmtPx(plan.entry)}` : 'Approve',
    tone: 'primary',
    locked: why ?? notTradeLock(a.notTrade),
    tip: plan ? `At the trigger, with the tape at go, Nova sends ${verb} ${size ?? '?'}${sized} @ ${fmtPx(plan.entry)} `
      + `with ${legs(plan)}. Withdrawn if the setup re-arms, fails or disarms.${ssr}`
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
  // A short plan stages on the ticket's Short side with its buy stop (ADR 048).
  const stage: PlanAction = plan?.side === 'short' ? {
    id: 'stage', label: 'Stage short in ticket', tone: 'primary', locked: a.stageLocked,
    tip: 'Fills this tab\'s ticket with a short: a sell limit at the entry for your size, with the plan\'s buy stop. '
      + 'It never sends.',
  } : {
    id: 'stage', label: 'Stage in ticket', tone: 'primary', locked: a.stageLocked,
    tip: 'Fills this tab\'s ticket with a buy limit at the entry for your size. It never sends.',
  };
  // A take-over always leaves Entry on You (ADR 042 draft): it never turns the stock into Auto-entry.
  const buyStays = `Entry stays on You: the bot enters nothing more on ${a.symbol}.`;
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
    // An entry still working, long or short (#778 step 5): cancelling it takes its exits with it.
    const entry = live.side === 'short' ? 'short' : 'buy';
    const exits = live.side === 'short' ? 'its buy stop and cover' : 'its stop and target';
    if (live.kind === 'approve') {
      return { actions: [{ id: 'cancel-approval', label: `Cancel the ${entry}`, tone: 'plain', locked: null,
        tip: `Cancels the ${entry} that has not filled; ${exits} go with it.` }], status: null };
    }
    if (live.kind === 'auto_entry') {
      return { actions: [{ id: 'auto-off', label: 'Auto-entry on · turn off', tone: 'plain', locked: null,
        tip: `Entry goes back to You and cancels the ${entry} that has not filled.` }], status: null };
    }
    return { actions: [{ id: 'take-over', label: 'Take over', tone: 'plain', locked: null,
      tip: `Nova cancels the bot's ${entry} that has not filled, with ${exits}. The stock leaves the bot's `
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
          tip: 'Entry goes back to You: Nova will not enter this stock, long or short.' }],
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
  // A short makes money as the price falls (ADR 048).
  const move = t.side === 'short' ? t.fill_price - t.exit_price : t.exit_price - t.fill_price;
  return ` · ${fmtPnl(move * t.qty)}`;
}
