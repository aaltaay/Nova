/**
 * The ticket's Live words (ADR 070 amendment 2026-11-20; the frozen Live board, R2-Trade-landscape). Pure, so it is
 * tested without a screen.
 *
 * The phone decides nothing about an order. The Live share limit is the desk's -- `/api/ibkr/status` `qty_cap`, the
 * cap on the desk's venue, null on Paper and Sim -- and the door cuts every Live place to it whatever the phone
 * sends (never a Flatten). These functions only make a button say what the door will send: no size over the limit
 * is offered, and a sell says the shares that go.
 */

/** The share counts the Quick ticket offers on Paper and Sim. */
export const QUICK_SIZES: readonly number[] = [100, 500, 1000];
const BIGGEST = QUICK_SIZES[QUICK_SIZES.length - 1];

/** Whole shares in the desk's way of writing them: 1,000. */
export function shareCount(n: number): string {
  return n.toLocaleString('en-US');
}

/**
 * Whether the limit is small enough to replace the size choices: then the ticket offers the sizes under it and the
 * limit itself, with the limit's words, and no typed size (the frozen board: one "1" and "Live limit: 1 share").
 */
export function limitBinds(cap: number | null): cap is number {
  return cap != null && cap <= BIGGEST;
}

/** The sizes a ticket offers under the share limit: every Quick size when none binds. */
export function sizesUnder(cap: number | null): number[] {
  if (!limitBinds(cap)) return [...QUICK_SIZES];
  return [...QUICK_SIZES.filter((n) => n < cap), cap];
}

/** The shares an order of `shares` sends under the limit. */
export function underCap(shares: number, cap: number | null): number {
  return cap != null && shares > cap ? cap : shares;
}

/**
 * The Quick size the buttons use: the one chosen, when the limit allows it. Otherwise never more than was chosen
 * where the row allows: the biggest size the row offers under the chosen one, and only when there is none (a
 * chosen size smaller than every size offered) the smallest. Real money never defaults to the limit itself.
 */
export function quickSizeUnder(chosen: number, cap: number | null): number {
  if (cap == null) return chosen;
  if (!limitBinds(cap)) return Math.min(chosen, cap);
  const row = sizesUnder(cap);
  const under = row.filter((n) => n <= chosen);
  return under.length ? under[under.length - 1] : row[0];
}

/** The frozen board's words for the desk's limit. */
export function liveLimitWords(cap: number): string {
  return `Live limit: ${shareCount(cap)} share${cap === 1 ? '' : 's'}. Raise it on the desk.`;
}

/**
 * The main line of a Live sell button (the frozen board: "LIVE SELL 1"): the shares that go, whether the button sells
 * half or all, and whether the limit cut it. LIVE takes the place of the half / all mark, so the line fits the
 * phone's narrowest button; the column says which it is, and the size row names the limit when it cuts.
 */
export function liveSellWords(shares: number, cap: number | null): string {
  return `LIVE SELL ${shareCount(underCap(shares, cap))}`;
}
