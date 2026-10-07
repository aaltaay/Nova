/**
 * A setup plan's calls before the trade, for each side (ADR 049): a long enters over its trigger and the chart says
 * ENTER NOW; a short sells under its trigger and the chart says SHORT NOW, except the SSR bounce, whose short rests
 * over the price for a buyer to lift. Every Nova mode trades a short as it trades a long (#778 step 5): Approve sends
 * it with its buy stop and cover, Auto-entry and the bot short it at the trigger with its buy stop. Pure:
 * `momentModel.ts` reads these.
 */
import { fmtPx } from './planMath';
import type { StockModeApproval, StockModeName, StockPlan } from './types';

export function isShortPlan(plan: StockPlan | null | undefined): boolean {
  return plan?.side === 'short';
}

/** The SSR bounce's short rests over the price (ADR 049): it is near from under, as a long is. */
function rests(plan: StockPlan): boolean {
  return plan.setup_type === 'ssr_bounce';
}

/** The call at the trigger: ENTER NOW for a long, SHORT NOW for a short. */
export function enterWord(plan: StockPlan): string {
  return isShortPlan(plan) ? 'SHORT NOW' : 'ENTER NOW';
}

/** Which way the price stands from the trigger while the setup is near. */
export function nearSide(plan: StockPlan): 'under' | 'over' {
  return isShortPlan(plan) && !rests(plan) ? 'over' : 'under';
}

/** Your click at a short's trigger: the short goes in with its buy stop. */
export const SHORT_ACT = ' Your click: stage the short with its buy stop.';

/** The sizes the words name: Approve's (the operator's approved size, else the plan's) and the one Nova sends. */
export interface WordQty { approve: number | null; nova: number | null }

/** A short plan's waiting words for each mode; null for a long plan (the model's own words). */
export function shortWaitingWords(plan: StockPlan, mode: StockModeName, near: string, trigger: string,
  qty: WordQty = { approve: null, nova: null }): [string, string] | null {
  if (!isShortPlan(plan)) return null;
  const ready = rests(plan)
    ? `${near}A short rests at ${trigger}: a buyer lifting the offer to it fills it, above the bid as SSR requires.`
    : `${near}Short under ${trigger}: the chart says SHORT NOW when it prints.`;
  const prints = rests(plan) ? `a buyer lifts it to ${trigger}` : `${trigger} prints`;
  const stop = fmtPx(plan.stop);
  const words: Record<StockModeName, [string, string]> = {
    signal: ['GET READY', ready],
    approve: ['APPROVE TO SEND', `Approve the plan and Nova sends short ${qty.approve ?? '?'} @ ${fmtPx(plan.entry)} `
      + 'with its buy stop and cover at the trigger.'],
    auto_entry: [`BOT SHORTS AT ${trigger}`, `${near}If ${prints} with the tape at go, the bot shorts ${qty.nova ?? '?'} `
      + `with its buy stop ${stop}. Every cover is yours.`],
    bot: ['THE BOT TRADES THIS', `${near}It shorts at the trigger and covers at ${fmtPx(plan.target)}, at its buy stop `
      + `${stop} or after 15 minutes.`],
  };
  return words[mode];
}

/** What an approval waiting for its trigger will send, for its side. */
export function approvedWords(plan: StockPlan, a: StockModeApproval): string {
  const when = `when ${fmtPx(plan.trigger)} prints with the tape at go.`;
  return isShortPlan(plan)
    ? `Nova sends short ${a.qty} @ ${fmtPx(a.entry)} with buy stop ${fmtPx(a.stop)} and cover ${fmtPx(a.target)} ${when}`
    : `Nova sends buy ${a.qty} @ ${fmtPx(a.entry)} with stop ${fmtPx(a.stop)} and target ${fmtPx(a.target)} ${when}`;
}

/** Your click at the trigger, for the mode: Approve sends it now, Signal only stages it. */
export function actWords(plan: StockPlan, mode: StockModeName, approveQty: number | null): string {
  const short = isShortPlan(plan);
  if (mode === 'approve') {
    return short ? ` Approve: short ${approveQty ?? '?'} now sends it with its buy stop and cover.`
      : ` Approve: buy ${approveQty ?? '?'} now sends it with its stop and target.`;
  }
  return short ? SHORT_ACT : ' Your click.';
}

/** Why Nova will not trade it by itself, as the chart's title; the day's cap counts both sides. */
export function blockedTitle(plan: StockPlan, mode: StockModeName, used: boolean, triggered: boolean): string {
  if (used) return 'THE BOT\'S TRADE TODAY IS USED';
  if (mode === 'bot') return triggered ? 'THE BOT IS NOT TRADING IT' : 'THE BOT WILL NOT TRADE THIS';
  const verb = isShortPlan(plan) ? 'SHORT' : 'BUY';
  return triggered ? `THE BOT IS NOT ${verb}ING IT` : `THE BOT WILL NOT ${verb} THIS`;
}
