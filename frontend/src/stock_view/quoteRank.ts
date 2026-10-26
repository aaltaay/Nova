/**
 * Where the Trader's symbol stands on the scanner lists (operator ask
 * 2026-09-30: "I need these tickers to show the current rank, especially in
 * the pre-market ... is it the fourth on the list, or is it number one?").
 *
 * Pure. A rank is the row's 1-based place in the list as the scanner serves it
 * -- the order the board shows before a column sort -- counted over the whole
 * list, before the board's exchange filter or chips. A list that does not hold
 * the symbol is left out. When the desk cannot say (no scanner feed, the
 * Scanner showing a saved day, no leaderboard at the Sim playhead) the answer
 * is `unknown` with the reason, never "not on a list".
 */
import type { LiveScannerFeed } from '../scanner';

export type RankListId = 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'large_cap';

export interface ListRank {
  list: RankListId;
  label: string;
  rank: number;
  total: number;
}

export type SymbolRanks =
  | { state: 'ranked'; ranks: ListRank[]; replay: boolean }
  | { state: 'unranked'; replay: boolean }
  | { state: 'unknown'; why: string };

type RankFeed = Pick<
  LiveScannerFeed,
  'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'historyDate' | 'replay'
>;

type ListKey = 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap';
type ListFeed = { readonly [K in ListKey]: readonly { symbol: string }[] };

const LISTS: readonly { list: RankListId; label: string; key: ListKey }[] = [
  { list: 'gappers', label: 'Gappers', key: 'gappers' },
  { list: 'gainers', label: 'Gainers', key: 'gainers' },
  { list: 'losers', label: 'Losers', key: 'losers' },
  { list: 'afterhours', label: 'After Hours', key: 'afterhours' },
  { list: 'large_cap', label: 'Large Cap', key: 'largeCap' },
];

/**
 * Why the desk cannot rank right now, or null when it can. The Trader's rank chip and the
 * Top 9 pop-up (top_nine/) both ask this, so they never disagree about a board.
 */
export function rankUnknownWhy(feed: Pick<RankFeed, 'historyDate' | 'replay'> | null | undefined): string | null {
  if (!feed) return 'No scanner feed in this window.';
  if (feed.historyDate) return `The Scanner is showing the saved board of ${feed.historyDate}, not today's.`;
  const replay = feed.replay ?? null;
  if (replay) {
    if (replay.gap) return 'No scanner board at the Sim playhead (a gap in the record).';
    if (replay.status === 'loading') return 'Loading the scanner board at the Sim playhead.';
    if (replay.status === 'error') {
      return `The scanner board at the Sim playhead did not load${replay.error ? `: ${replay.error}` : '.'}`;
    }
  }
  return null;
}

/** One list's rows in served order: row i is rank i + 1. */
export function scannerListRows<T extends { symbol: string }>(feed: ListFeed, list: RankListId): readonly T[] {
  const key = LISTS.find((l) => l.list === list)?.key;
  return ((key ? feed[key] : undefined) as readonly T[] | undefined) ?? [];
}

export function symbolRanks(symbol: string, feed: RankFeed | null | undefined): SymbolRanks {
  const why = rankUnknownWhy(feed);
  if (why || !feed) return { state: 'unknown', why: why ?? 'No scanner feed in this window.' };
  const replay = feed.replay ?? null;
  const sym = symbol.trim().toUpperCase();
  const ranks: ListRank[] = [];
  for (const { list, label } of LISTS) {
    const rows = scannerListRows(feed, list);
    if (!rows.length) continue;
    const at = rows.findIndex((r) => r.symbol?.toUpperCase() === sym);
    if (at >= 0) ranks.push({ list, label, rank: at + 1, total: rows.length });
  }
  return ranks.length
    ? { state: 'ranked', ranks, replay: replay != null }
    : { state: 'unranked', replay: replay != null };
}

function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

/** The hover text for one list's rank. */
export function rankTip(r: ListRank, replay: boolean): string {
  const when = replay ? ' at the Sim playhead' : '';
  return (
    `${ordinal(r.rank)} of ${r.total} on ${r.label}${when}.\n`
    + "Counted in the scanner's own order -- the board's order before you sort a column -- "
    + 'over the whole list, before the exchange filter or chips.'
  );
}
