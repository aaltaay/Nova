/** The plan box's arithmetic and words (ADR 036). Pure: every number here comes from the read or the
 * operator's own risk per trade; nothing is estimated. */
import { STOCK_READ_RISK_MAX_USD } from './constants';
import type { ReadState, SetupLane, StockPlan } from './types';

const SETUP_NAMES: Record<string, string> = {
  first_pullback: 'First pullback',
  bull_flag: 'Bull flag',
  flat_top_breakout: 'Flat-top breakout',
  red_to_green: 'Red to green',
  gap_and_go: 'Gap and Go',
  micro_pullback: 'Micro pullback',
};

export function setupName(setupType: string | null | undefined): string {
  if (!setupType) return 'Setup';
  return SETUP_NAMES[setupType] ?? setupType.replace(/_/g, ' ');
}

const SETUP_SHORT: Record<string, string> = {
  first_pullback: 'Pullback', bull_flag: 'Flag', flat_top_breakout: 'Flat top', red_to_green: 'R→G',
};

/** The setup in a word or two, where a tile or a one-line plan has no room for its name. */
export function setupShort(setupType: string | null | undefined): string {
  return SETUP_SHORT[setupType ?? ''] ?? setupName(setupType);
}

/** A price as the desk shows it: 4 decimals under $1, else 2. */
export function fmtPx(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—';
  return Math.abs(p) < 1 ? p.toFixed(4) : p.toFixed(2);
}

/** A step between two prices (a risk, a cent, a distance) in the decimals of the price it is on. */
export function fmtStep(step: number | null | undefined, ref: number | null | undefined): string {
  if (step === null || step === undefined || !Number.isFinite(step)) return '—';
  return step.toFixed(ref !== null && ref !== undefined && Math.abs(ref) < 1 ? 4 : 2);
}

export function fmtUsd(usd: number | null | undefined): string {
  if (usd === null || usd === undefined || !Number.isFinite(usd)) return '—';
  return `$${Math.round(usd).toLocaleString('en-US')}`;
}

export function rrText(rr: number | null): string {
  return rr === null ? '— : 1' : `${rr.toFixed(1)} : 1`;
}

/** Whole shares the operator's risk per trade buys at this risk per share; null when it buys none. */
export function sizeFor(riskUsd: number, risk: number | null): number | null {
  if (risk === null || !(risk > 0) || !(riskUsd > 0)) return null;
  const n = Math.floor(riskUsd / risk + 1e-9);
  return n >= 1 ? n : null;
}

export function parseRiskUsd(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw.replace(/[$,\s]/g, '')) : NaN;
  return Number.isFinite(n) && n > 0 && n <= STOCK_READ_RISK_MAX_USD ? Math.round(n * 100) / 100 : null;
}

/** "1/2" for a forming setup waiting on "1 more red or doji candle"; null when it says nothing countable. */
export function formingProgress(lane: SetupLane | null | undefined): string | null {
  const f = lane?.forming;
  if (!f || !f.waiting) return null;
  const m = /^(\d+) more/.exec(f.waiting);
  if (!m) return null;
  const have = Math.max(0, Math.round(f.bars));
  return `${have}/${have + Number(m[1])}`;
}

/** The lane the plan follows (the read names its setup type); null for a hand plan. */
export function planLane(plan: StockPlan | null, lanes: SetupLane[]): SetupLane | null {
  if (!plan || plan.source !== 'setup' || !plan.setup_type) return null;
  return lanes.find(l => l.setup_type === plan.setup_type) ?? null;
}

/** The badge after the plan's name. */
export function planBadge(plan: StockPlan, lane: SetupLane | null): string {
  if (plan.source === 'manual') return 'NO SETUP';
  if (plan.state === 'forming') {
    const prog = formingProgress(lane);
    return prog ? `FORMING ${prog}` : 'FORMING';
  }
  if (plan.state === 'near' && lane?.distance !== null && lane?.distance !== undefined) {
    return `NEAR ${fmtStep(lane.distance, plan.entry)}`;
  }
  return plan.state.toUpperCase();
}

/** The one-line plan's badge: the setup and where it stands ("FLAG 1/2", "PULLBACK NEAR 0.03"). */
export function planBadgeShort(plan: StockPlan, lane: SetupLane | null): string {
  if (plan.source === 'manual') return 'YOUR PLAN';
  const state = planBadge(plan, lane).replace(/^FORMING /, '');
  return `${setupShort(plan.setup_type)} ${state}`.toUpperCase();
}

/** The stop cap the risk check measured against ("risk 0.11 within the 0.20 cap"). */
export function stopCap(plan: StockPlan): number | null {
  const c = plan.checks.find(x => x.id === 'risk');
  const m = c ? /the ([\d.]+) (?:stop )?cap/.exec(c.text) : null;
  return m ? Number(m[1]) : null;
}

export function checkGlyph(state: ReadState): string {
  return state === 'ok' ? '✓' : state === 'bad' ? '✗' : state === 'warn' ? '!' : state === 'info' ? '·' : '?';
}

/** The sub-line under each of the five numbers. */
export function planSubLines(plan: StockPlan, riskUsd: number, size: number | null): Record<string, string> {
  const risk = plan.risk;
  const at2 = plan.entry !== null && risk !== null ? plan.entry + 2 * risk : null;
  let target = plan.target_rule;
  if (plan.target !== null && at2 !== null && Math.abs(plan.target - at2) < 0.005) {
    target = `entry + 2 × ${fmtStep(risk, plan.entry)}`;
  } else if (/pole high/.test(plan.target_rule)) {
    target = 'the pole high';
  } else if (/leg high/.test(plan.target_rule)) {
    target = 'the leg high';
  } else if (/high of day/.test(plan.target_rule)) {
    target = 'the high of day';
  }
  const cap = stopCap(plan);
  const riskCheck = plan.checks.find(x => x.id === 'risk');
  const capLine = cap === null
    ? (riskCheck?.text ?? '')
    : `${riskCheck?.state === 'bad' ? '>' : '≤'} ${fmtStep(cap, plan.entry)} cap ${checkGlyph(riskCheck?.state ?? 'unknown')}`;
  const entry = plan.source === 'manual'
    ? 'your entry'
    : plan.trigger !== null && plan.entry !== null && plan.entry > plan.trigger
      ? `${fmtPx(plan.trigger)} + ${fmtStep(plan.entry - plan.trigger, plan.entry)}`
      : plan.entry_rule;
  return {
    entry,
    stop: plan.stop_rule.replace(/^the /, ''),
    target,
    risk: capLine,
    size: size === null
      ? `at ${fmtUsd(riskUsd)} risk`
      : `at ${fmtUsd(riskUsd)} risk · ${fmtUsd(size * (plan.entry ?? 0))}`,
  };
}

export interface RulerMark {
  pct: number;
  label: string;
  kind: string;
}

export interface RulerLayout {
  entryPct: number;
  stopPct: number;
  targetPct: number;
  marks: RulerMark[];
  /** The last price on the ruler; `edge` when it sits past either end. */
  now: { pct: number; edge: 'low' | 'high' | null } | null;
}

/** Stop at the left end, the target at the right, everything between placed by price. */
export function rulerLayout(plan: StockPlan, price: number | null): RulerLayout | null {
  const { stop, entry, target } = plan;
  if (stop === null || entry === null || target === null || !(target > stop)) return null;
  const pad = (target - stop) * 0.06;
  const lo = stop - pad;
  const hi = target + pad;
  const at = (p: number) => Math.min(100, Math.max(0, ((p - lo) / (hi - lo)) * 100));
  let now: RulerLayout['now'] = null;
  if (price !== null && Number.isFinite(price)) {
    now = { pct: at(price), edge: price < lo ? 'low' : price > hi ? 'high' : null };
  }
  return {
    stopPct: at(stop),
    entryPct: at(entry),
    targetPct: at(target),
    marks: plan.marks.map(m => ({ pct: at(m.price), label: fmtPx(m.price), kind: m.kind })),
    now,
  };
}

/** The line under the buttons: what the plan is waiting on, or what the operator can do. */
export function planFootnote(plan: StockPlan, lane: SetupLane | null): string {
  if (plan.source === 'manual') {
    return plan.stop === null
      ? 'name a stop under your entry'
      : 'drag the entry or stop on the 1-minute chart; the target stays 2R';
  }
  if (plan.state === 'forming') {
    const f = lane?.forming;
    if (f?.waiting) return `provisional: arms after ${f.waiting}`;
    if (f?.blocked) return `provisional: blocked, ${f.blocked}`;
    return 'provisional until the setup arms';
  }
  if (plan.tape) return `tape ${plan.tape.verdict.toUpperCase()}${plan.tape.reasons[0] ? `: ${plan.tape.reasons[0]}` : ''}`;
  return plan.reason;
}
