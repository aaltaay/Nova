/**
 * A setup plan's calls before the trade, for each side (ADR 049): a long enters over its trigger and the chart says
 * ENTER NOW; a short sells under its trigger and the chart says SHORT NOW, except the SSR bounce, whose short rests
 * over the price for a buyer to lift. Every entry is the operator's own click: the strategies only watch (ADR 072).
 * Pure: `momentModel.ts` reads these.
 */
import type { StockPlan } from './types';

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

/** A short plan's GET READY words; null for a long plan (the model's own words). */
export function shortWaitingWords(plan: StockPlan, near: string, trigger: string): [string, string] | null {
  if (!isShortPlan(plan)) return null;
  return ['GET READY', rests(plan)
    ? `${near}A short rests at ${trigger}: a buyer lifting the offer to it fills it, above the bid as SSR requires.`
    : `${near}Short under ${trigger}: the chart says SHORT NOW when it prints.`];
}

/** Your click at the trigger: a long's, or a short's with its buy stop. */
export function actWords(plan: StockPlan): string {
  return isShortPlan(plan) ? SHORT_ACT : ' Your click.';
}
