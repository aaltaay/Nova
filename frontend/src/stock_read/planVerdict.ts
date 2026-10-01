/**
 * Whether the plan is a trade (operator report, 2026-09-29: "So why does it think this is a good trade
 * when it's obviously not?"): the plan's pillar count ("grade C · 1/5"), every reason a setup plan is
 * not a trade, and a setup that already played out -- off the wire, and in the words the plan card,
 * its badge and the chart use. Pure. Nothing here places or blocks an order: the words lock the plan's
 * own Stage and Approve buttons and say why (`data-why`).
 */
import { isThin } from '../setups';
import { hhmmEt } from './timeWords';
import type { PlanPillars, PlanResult, PlanTrade, StockPlan } from './types';

type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** The plan's verdict fields off the wire; each null when the wire lacks or mistypes it. */
export function normalizePlanVerdict(p: Obj): { pillars: PlanPillars | null; trade: PlanTrade | null;
  result: PlanResult | null } {
  const pc = obj(p.pillars);
  const passed = num(pc?.passed);
  const total = num(pc?.total);
  const pillars = passed !== null && total !== null ? { passed, known: num(pc?.known) ?? passed, total } : null;
  const t = obj(p.trade);
  const reasons = Array.isArray(t?.reasons) ? t.reasons.filter((x): x is string => typeof x === 'string') : [];
  const trade = t && typeof t.ok === 'boolean' ? { ok: t.ok, reasons } : null;
  const r = obj(p.result);
  const outcome = r?.outcome;
  const result: PlanResult | null = r && (outcome === 'target_first' || outcome === 'stop_first')
    && typeof r.text === 'string'
    ? { outcome, at: num(r.at), r: num(r.r), text: r.text }
    : null;
  return { pillars, trade, result };
}

/** A setup plan on a stock too thin to trade (2026-10-01): no plan is drawn, the badge says so. */
export function thinPlan(plan: StockPlan | null | undefined): boolean {
  return !!plan && plan.source === 'setup' && isThin(plan.liquidity);
}

/** The plan's grade chip, "C 1/5" -- it never shrinks, so the rail always shows it; null without a grade. */
export function gradeChip(plan: StockPlan): string | null {
  if (!plan.grade) return null;
  return plan.pillars ? `${plan.grade} ${plan.pillars.passed}/${plan.pillars.total}` : plan.grade;
}

/** What the grade chip means, on hover. */
export function gradeTip(plan: StockPlan): string {
  const p = plan.pillars;
  const unknown = p && p.known < p.total ? ` (${p.total - p.known} not known)` : '';
  const head = p ? `Grade ${plan.grade}: ${p.passed} of ${p.total} pillars pass${unknown}.` : `Grade ${plan.grade}.`;
  return `${head}\nThe Five Pillars: price, up on the day, relative volume, float, news. A = all five pass, `
    + 'B = four, C = three or fewer: not a trade.';
}

/** Why the plan is not a trade, as one sentence; null when it is one, or the plan is the operator's own. */
export function notATrade(plan: StockPlan | null): string | null {
  if (!plan?.trade || plan.trade.ok) return null;
  const why = plan.trade.reasons.join('; ');
  return why ? `Not a trade: ${why}.` : 'Not a trade.';
}

function scoreText(r: number | null): string {
  return r !== null ? `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R` : '';
}

/** A played-out setup's badge: "STOP FIRST 08:08 · −1.00R". */
export function resultBadge(result: PlanResult): string {
  const what = result.outcome === 'target_first' ? 'TARGET FIRST' : 'STOP FIRST';
  const at = result.at !== null ? ` ${hhmmEt(result.at)}` : '';
  const score = scoreText(result.r);
  return `${what}${at}${score ? ` · ${score}` : ''}`;
}

/** The same on the one-line plan, where the rail has no room for the time: "STOP FIRST −1.00R". */
export function resultBadgeShort(result: PlanResult): string {
  const score = scoreText(result.r);
  return `${result.outcome === 'target_first' ? 'TARGET FIRST' : 'STOP FIRST'}${score ? ` ${score}` : ''}`;
}
