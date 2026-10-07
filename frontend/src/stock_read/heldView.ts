/**
 * What the desk draws for the trade you hold (ADR 036 amendment 2026-10-01), pure: Level 2's NEXT and STOP,
 * the 10-second chart's lines (operator: "lets move these targets ... to the 10 seconds chart"), and the
 * plan box's ruler while you hold -- from your average past the stop to the level after next.
 */
import type { DepthMarker } from '../ibkr';
import type { PriceLineSpec } from './chartShapes';
import { RULER_DEFAULT_WIDTH_PX, SETUP_COLORS } from './constants';
import { CHART_ROLES, ROLE_WORDS, rowOf, type HeldRole, type StockHeld } from './heldRead';
import { fmtPx, placeRulerLabels, type RulerMark } from './planMath';

const ROLE_COLORS: Record<HeldRole, string> = {
  then: 'rgba(48, 209, 88, 0.6)',
  next: SETUP_COLORS.target,
  now: '#ffd60a',
  through: SETUP_COLORS.round,
  broke: SETUP_COLORS.level,
  support: SETUP_COLORS.level,
  resistance: SETUP_COLORS.level,
  stop: SETUP_COLORS.stop,
  cost: SETUP_COLORS.trigger,
};

/** NEXT with the asks and the STOP with the bids, on Level 2; a short's mirror: STOP ↑ with the asks (its buy
 * stop over the price) and NEXT ↓ with the bids (ADR 048). */
export function heldMarkers(held: StockHeld | null): DepthMarker[] {
  if (!held) return [];
  const short = held.side === 'short';
  const out: DepthMarker[] = [];
  const next = rowOf(held, 'next');
  if (held.stop) {
    const nova = held.stop.source === 'nova';
    const what = short ? 'buy stop' : 'stop';
    out.push({
      id: 'stop', price: held.stop.price, label: `${short ? 'STOP ↑' : 'STOP'} ${fmtPx(held.stop.price)}`,
      color: SETUP_COLORS.stop, working: nova, rests: short ? 'ask' : 'bid',
      tip: nova ? `Nova's ${what} order rests here.` : held.stop.source === 'yours'
        ? `Your ${what}. Only a plan: no order stands behind it.`
        : `The ${what} Nova proposes (${held.stop.rule}). Only a plan: no order stands behind it.`,
    });
  }
  if (next) {
    out.push({
      id: 'target', price: next.price, label: `${short ? 'NEXT ↓' : 'NEXT'} ${fmtPx(next.price)}`,
      color: SETUP_COLORS.target, working: false, rests: short ? 'bid' : 'ask',
      tip: `The next level ${short ? 'under' : 'over'} the price: ${next.text}.`,
    });
  }
  return out;
}

/** The 10-second chart's lines while you hold: each ladder row but the price, its name in the edge column. */
export function heldLines(held: StockHeld | null): PriceLineSpec[] {
  if (!held) return [];
  return held.ladder
    .filter(r => CHART_ROLES.has(r.role))
    .map((r, i) => ({
      id: `held-${r.role}-${i}`,
      price: r.price,
      color: ROLE_COLORS[r.role],
      width: r.role === 'stop' || r.role === 'cost' || r.role === 'next' ? 2 : 1,
      style: r.role === 'cost' || (r.role === 'stop' && held.stop?.source === 'nova') ? 'solid'
        : r.role === 'broke' || r.role === 'through' ? 'dotted' : 'dashed',
      title: r.role === 'cost' ? `COST ${fmtPx(r.price)}` : `${ROLE_WORDS[r.role]} ${fmtPx(r.price)}`,
      axisLabel: true,
    }));
}

export interface HeldRulerLayout {
  costPct: number;
  stopPct: number | null;
  endPct: number;
  nowPct: number | null;
  /** Locked in by a stop over your average; null when the stop is under it (or none). */
  locked: [number, number] | null;
  /** What the stop gives back from here (or the risk to it, while the price is under your average + stop). */
  risk: [number, number] | null;
  /** To the next level. */
  reward: [number, number] | null;
  /** From the next level to the one after (dotted). */
  ahead: [number, number] | null;
  marks: RulerMark[];
}

/** A held mark's label rank, as one of the plan ruler's kinds (`RULER_LABEL_RANK`). */
const RANK_AS: Readonly<Record<string, string>> = { next: 'wall', broke: 'hod', through: 'level', target: 'round', support: 'round' };

/** The held ruler: your average (●) at the left unless the stop is under it, the level after next at the
 * right; labels that would touch a stronger one are left off (their ticks stay). A short's runs the other way
 * (ADR 048): the higher prices -- its buy stop -- at the left, the levels under the price at the right. */
export function heldRuler(held: StockHeld, widthPx: number | null = null): HeldRulerLayout | null {
  const short = held.side === 'short';
  const price = held.price;
  const stop = held.stop?.price ?? null;
  const next = rowOf(held, 'next')?.price ?? null;
  const then = rowOf(held, 'then')?.price ?? null;
  const fallback = price !== null
    ? (short ? Math.min(price, held.avg) * 0.98 : Math.max(price, held.avg) * 1.02) : null;
  const end = then ?? next ?? fallback;
  const left = short
    ? Math.max(held.avg, stop ?? held.avg, price ?? held.avg)
    : Math.min(held.avg, stop ?? held.avg, price ?? held.avg);
  if (end === null || !(short ? end < left : end > left)) return null;
  const pad = Math.abs(end - left) * 0.06;
  const lo = Math.min(left, end) - pad;
  const hi = Math.max(left, end) + pad;
  // Pct along the ruler: price up for a long, price down for a short (the trade's way is always right).
  const at = (p: number) => Math.min(100, Math.max(0, ((short ? hi - p : p - lo) / (hi - lo)) * 100));
  const span = (a: number | null, b: number | null): [number, number] | null =>
    a !== null && b !== null && at(b) > at(a) ? [at(a), at(b)] : null;
  // The stop has locked money in: over your average for a long, under it for a short.
  const over = stop !== null && (short ? stop <= held.avg : stop >= held.avg);
  const between = (p: number) => at(p) > at(left) && at(p) < at(end);
  const shelf = short ? 'resistance' : 'support';
  const marks = [
    ...held.broke.map(b => ({ pct: at(b.round), label: `$${b.round.toFixed(2)} ✓`, kind: 'broke' })),
    ...held.through.map(b => ({ pct: at(b.round), label: `$${b.round.toFixed(2)}`, kind: 'through' })),
    ...(next !== null && then !== null ? [{ pct: at(next), label: fmtPx(next), kind: 'next' }] : []),
    ...(held.target && between(held.target.price) ? [{ pct: at(held.target.price), label: '2R', kind: 'target' }] : []),
    ...held.ladder.filter(r => r.role === shelf).map(r => ({ pct: at(r.price), label: fmtPx(r.price), kind: 'support' })),
  ];
  // The placer ranks by the plan's kinds: each held kind takes the rank of one (NEXT first, like a seller).
  const placed = placeRulerLabels(
    marks.map(m => ({ ...m, kind: RANK_AS[m.kind] ?? 'round' })),
    widthPx && widthPx > 0 ? widthPx : RULER_DEFAULT_WIDTH_PX,
    at(price ?? held.avg),
  ).map((m, i) => ({ ...m, kind: marks[i].kind }));
  const best = (a: number | null, b: number | null) =>
    a === null ? b : b === null ? a : (short ? Math.min(a, b) : Math.max(a, b));
  return {
    costPct: at(held.avg),
    stopPct: stop !== null ? at(stop) : null,
    endPct: at(end),
    nowPct: price !== null ? at(price) : null,
    locked: over ? span(held.avg, stop) : null,
    risk: over ? span(stop, price) : span(stop, held.avg),
    reward: span(over ? best(price ?? stop ?? held.avg, stop ?? held.avg) : best(price ?? held.avg, held.avg), next ?? end),
    ahead: next !== null && then !== null ? span(next, then) : null,
    marks: placed,
  };
}
