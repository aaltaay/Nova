/**
 * The plan's levels and what stands behind each (ADR 036), pure: drawn dashed on the charts while they are only a
 * plan, the entry solid once shares are held, and as ENTRY / STOP / TARGET / T2 rows in the Level 2 book (T2: the
 * second half's target, #845). Nova places nothing behind them: the strategies only watch (ADR 072).
 */
import type { DepthMarker } from '../ibkr';
import { SETUP_COLORS } from './constants';
import { judgedLevels, type MomentInputs } from './momentModel';
import { heldAnyQty } from './momentShort';
import { fmtPx } from './planMath';
import { thinPlan } from './planVerdict';

/** `plan`: only the plan; `held`: shares are held, so the plan's entry is in effect. */
export type Behind = 'plan' | 'held';

export interface OrderLevel {
  price: number;
  behind: Behind;
}

export interface OrderLevels {
  entry: OrderLevel | null;
  stop: OrderLevel | null;
  target: OrderLevel | null;
  /** The second half's target (#845); null (or absent) when every share sells at target 1. */
  target2?: OrderLevel | null;
}

function level(price: number | null, behind: Behind): OrderLevel | null {
  return price !== null && Number.isFinite(price) ? { price, behind } : null;
}

/** The levels the charts and Level 2 draw: the levels a held position is judged by, else the plan's. */
export function orderLevels(i: MomentInputs): OrderLevels | null {
  const plan = i.read?.plan ?? null;
  if (heldAnyQty(i) > 0) {
    // The chart draws the position's own cost; the plan's entry turns solid once shares are held (long or short).
    const lv = judgedLevels(i);
    return {
      entry: level(lv?.entry ?? null, 'held'),
      stop: level(lv?.stop ?? null, 'plan'),
      target: level(lv?.target ?? null, 'plan'),
    };
  }
  // A setup plan too thin to trade is no plan (2026-10-01): nothing drawn, nothing marked in Level 2.
  if (!plan || thinPlan(plan)) return null;
  return {
    entry: level(plan.entry, 'plan'), stop: level(plan.stop, 'plan'), target: level(plan.target, 'plan'),
    target2: level(plan.target2 ?? null, 'plan'),
  };
}

type MarkId = 'entry' | 'stop' | 'target' | 'target2';

const TIPS: Record<MarkId, Partial<Record<Behind, string>>> = {
  entry: {
    plan: "The plan's entry, a buy limit here. Only a plan: no order stands behind it.",
    held: "Shares are held: the plan's entry is in effect.",
  },
  stop: { plan: "The plan's stop. Only a plan: no order stands behind it." },
  target: { plan: "The plan's target. Only a plan: no order stands behind it." },
  target2: {
    plan: "The plan's target 2: the rest sells here after the first half. Only a plan: no order stands behind it.",
  },
};

const TIPS_SHORT: Record<MarkId, Partial<Record<Behind, string>>> = {
  entry: {
    plan: "The plan's short entry, a sell limit here that goes out with its buy stop. Only a plan: no order stands behind it.",
    held: 'Shares are held short: the plan\'s entry is in effect.',
  },
  stop: { plan: "The plan's buy stop over the entry. Only a plan: no order stands behind it." },
  target: { plan: "The plan's cover target. Only a plan: no order stands behind it." },
  target2: {
    plan: "The plan's cover 2: the rest covers here after the first half. Only a plan: no order stands behind it.",
  },
};

/** ENTRY / STOP / TARGET / T2 for the Level 2 book (T2: target 2, the second half's, #845); a short plan's SHORT,
 * STOP ↑, TARGET ↓ and T2 ↓ (ADR 048): its entry sells and its buy stop sits over the price with the asks, its
 * cover targets under it with the bids. */
export function level2Markers(levels: OrderLevels | null, side: 'long' | 'short' = 'long'): DepthMarker[] {
  if (!levels) return [];
  const short = side === 'short';
  const words: Record<MarkId, string> = short
    ? { entry: 'SHORT', stop: 'STOP ↑', target: 'TARGET ↓', target2: 'T2 ↓' }
    : { entry: 'ENTRY', stop: 'STOP', target: 'TARGET', target2: 'T2' };
  const tips = short ? TIPS_SHORT : TIPS;
  const out: DepthMarker[] = [];
  const add = (id: MarkId, lv: OrderLevel | null | undefined, color: string, rests: 'bid' | 'ask') => {
    if (!lv) return;
    out.push({
      id,
      price: lv.price,
      label: `${words[id]} ${fmtPx(lv.price)}`,
      color,
      working: lv.behind !== 'plan',
      rests,
      tip: tips[id][lv.behind] ?? '',
    });
  };
  add('entry', levels.entry, SETUP_COLORS.trigger, short ? 'ask' : 'bid');
  add('stop', levels.stop, SETUP_COLORS.stop, short ? 'ask' : 'bid');
  add('target', levels.target, SETUP_COLORS.target, short ? 'bid' : 'ask');
  add('target2', levels.target2, SETUP_COLORS.target, short ? 'bid' : 'ask');
  return out;
}

/** A price line's title for the level and what stands behind it; a short's SHORT, STOP ↑ and TARGET ↓ (ADR 048).
 * The plan's two targets (#845) are TARGET 1 and TARGET 2. */
export function levelTitle(id: 'entry' | 'stop' | 'target' | 'target2', behind: Behind, short = false): string {
  const entry = short ? 'SHORT' : 'ENTRY';
  const stop = short ? 'STOP ↑' : 'STOP';
  const arrow = short ? ' ↓' : '';
  if (id === 'entry') return behind === 'held' ? `${entry} · held` : entry;
  if (id === 'stop') return `${stop} · plan`;
  return `TARGET ${id === 'target2' ? 2 : 1}${arrow} · plan`;
}
