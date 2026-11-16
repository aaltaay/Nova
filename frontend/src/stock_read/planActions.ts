/**
 * The plan card's buttons (ADR 036), pure: Stage in ticket before the trade (a short plan's "Stage short in ticket",
 * ADR 048) and Stage sell while you hold, each with why it cannot act now. Both only fill this tab's ticket and never
 * send: who trades the stock is the operator (ADR 072).
 */
import { heldQty, judgedLevels, type Moment, type MomentInputs } from './momentModel';
import { fmtPx } from './planMath';

export type PlanActionId = 'stage' | 'stage-sell';

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
  /** Stage in ticket's own lock (the plan's entry, stop and size, or why it is not a trade). */
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

/** The plan card's button for the moment: Stage sell while you hold, else Stage in ticket. */
export function planActions(a: PlanActionsInput): PlanAction[] {
  const qty = heldQty(a.inputs);
  if (qty > 0) return [stageSell(a, qty)];
  const plan = a.inputs.read?.plan ?? null;
  // A short plan stages on the ticket's Short side with its buy stop (ADR 048).
  return [plan?.side === 'short' ? {
    id: 'stage', label: 'Stage short in ticket', tone: 'primary', locked: a.stageLocked,
    tip: 'Fills this tab\'s ticket with a short: a sell limit at the entry for your size, with the plan\'s buy stop. '
      + 'It never sends.',
  } : {
    id: 'stage', label: 'Stage in ticket', tone: 'primary', locked: a.stageLocked,
    tip: 'Fills this tab\'s ticket with a buy limit at the entry for your size. It never sends.',
  }];
}
