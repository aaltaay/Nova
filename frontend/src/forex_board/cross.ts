/**
 * The Forex page's pair arithmetic (ADR 061), as the backend's (forex_board/prices.py): a pair's move from its two
 * currencies' moves against the dollar -- a cross rate is the ratio of the two dollar rates -- and each currency's
 * strength against an even mix of the others. Percent points in, percent points out.
 */

/** The move of A/B from A's and B's moves against the dollar. */
export function cross(a: number, b: number): number {
  return ((1 + a / 100) / (1 + b / 100) - 1) * 100;
}

/** `{code: strength}` -- each against an even mix of the others (the dollar's move against itself is 0). */
export function strengths(moves: Record<string, number>): Record<string, number> {
  const codes = Object.keys(moves);
  if (codes.length < 2) return {};
  return Object.fromEntries(codes.map((a) => [
    a, codes.filter((b) => b !== a).reduce((sum, b) => sum + cross(moves[a], moves[b]), 0) / (codes.length - 1),
  ]));
}
