/**
 * The targets on the "Nova takes the exit" sheet (#681): how the shares split into two halves and what is
 * wrong with a target, in the words the backend refuses with (`stock_mode/exit_targets.py`,
 * `execution/exit_oco.py`). Pure.
 *
 * The operator's material sells half at target 1 and the rest at target 2, the stop left where it is after
 * the first half. The first half is the share count times `fraction` (0.5 unless the read names another),
 * rounded down -- an odd count gives the first half the smaller part -- and a position the rounding leaves
 * one half empty of (a single share), or no target 2, sells whole at target 1.
 */
import { fmtPx } from './planMath';
import type { StockModeTrade } from './types';

export const TARGET1_FRACTION_DEFAULT = 0.5;

export interface ExitTargets {
  target: number;
  target2: number | null;
  target1_fraction: number | null;
}

/** `[first half, second half]` in whole shares; a second half of 0 sells everything at target 1. */
export function splitHalves(qty: number, target1: number | null, target2: number | null,
  fraction: number | null | undefined, short: boolean): [number, number] {
  const shares = Math.floor(qty + 1e-9);
  if (!(shares > 0)) return [0, 0];
  const beyond = target1 !== null && target2 !== null && (short ? target2 < target1 : target2 > target1);
  if (!beyond) return [shares, 0];
  const part = fraction !== null && fraction !== undefined && fraction > 0 && fraction < 1
    ? fraction : TARGET1_FRACTION_DEFAULT;
  const first = Math.floor(shares * part + 1e-9);
  if (first < 1 || first >= shares) return [shares, 0];
  return [first, shares - first];
}

/** What the targets rest as: `LMT 6.12 x 50 and LMT 6.96 x 50`, or `LMT 6.12 x 100` when every share sells at target
 * 1 (no target 2, or one share). Nova's exit sheet and Approve's card say their halves in these words. */
export function limitWords(qty: number, target1: number, target2: number | null, fraction: number | null | undefined,
  short: boolean): string {
  const [first, second] = splitHalves(qty, target1, target2, fraction, short);
  return `LMT ${fmtPx(target1)} x ${first}${second && target2 !== null ? ` and LMT ${fmtPx(target2)} x ${second}` : ''}`;
}

/** A Nova trade's two limits as they rest (`LMT 4.52 x 76 and LMT 4.80 x 77`): the shares its backend split; null
 * for a trade that sells every share at target 1. */
export function tradeLimits(t: StockModeTrade): string | null {
  if (t.target === null || t.target2 == null || !t.target1_qty || !t.target2_qty) return null;
  return `LMT ${fmtPx(t.target)} x ${t.target1_qty} and LMT ${fmtPx(t.target2)} x ${t.target2_qty}`;
}

/** What is wrong with the sheet's targets, or null. */
export function targetProblem(short: boolean, price: number | null, stop: number | null, target1: number | null,
  target2: number | null): string | null {
  if (target1 === null) return target2 === null ? null : 'Target 2 needs a target 1 beside it.';
  const side = short ? 'under' : 'over';
  if (price !== null && (short ? target1 >= price : target1 <= price)) {
    return `Target 1 ${fmtPx(target1)} is not ${side} the price ${fmtPx(price)}: it would ${short ? 'cover' : 'sell'} `
      + 'at once.';
  }
  if (stop !== null && (short ? target1 >= stop : target1 <= stop)) {
    return `Target 1 ${fmtPx(target1)} must be ${side} the ${short ? 'buy stop' : 'stop'} ${fmtPx(stop)}.`;
  }
  if (target2 !== null && (short ? target2 >= target1 : target2 <= target1)) {
    return `Target 2 ${fmtPx(target2)} must be ${side} target 1 ${fmtPx(target1)}.`;
  }
  return null;
}

/** A read's target the sheet may start from: on the right side of the price (and of `after`, when given). */
export function usableTarget(short: boolean, value: number | null | undefined, price: number | null,
  after: number | null = null): number | null {
  if (value === null || value === undefined || !(value > 0)) return null;
  if (price !== null && (short ? value >= price : value <= price)) return null;
  if (after !== null && (short ? value >= after : value <= after)) return null;
  return value;
}

/** `[target 1, target 2]` the sheet starts from: the read's targets still ahead of the price, in order. A target
 * the price already passed gives its place to the next one, which then sells every share. */
export function startTargets(short: boolean, target1: number | null | undefined, target2: number | null | undefined,
  price: number | null): [number | null, number | null] {
  const first = usableTarget(short, target1, price);
  const second = usableTarget(short, target2, price, first);
  return first === null ? [second, null] : [first, second];
}
