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

const LISTS: readonly { list: RankListId; label: string; key: keyof RankFeed }[] = [
  { list: 'gappers', label: 'Gappers', key: 'gappers' },
  { list: 'gainers', label: 'Gainers', key: 'gainers' },
  { list: 'losers', label: 'Losers', key: 'losers' },
  { list: 'afterhours', label: 'After Hours', key: 'afterhours' },
  { list: 'large_cap', label: 'Large Cap', key: 'largeCap' },
];

export function symbolRanks(symbol: string, feed: RankFeed | null | undefined): SymbolRanks {
  if (!feed) return { state: 'unknown', why: 'No scanner feed in this window.' };
  if (feed.historyDate) {
    return { state: 'unknown', why: `The Scanner is showing the saved board of ${feed.historyDate}, not today's.` };
  }
  const replay = feed.replay ?? null;
  if (replay) {
    if (replay.gap) return { state: 'unknown', why: 'No scanner board at the Sim playhead (a gap in the record).' };
    if (replay.status === 'loading') return { state: 'unknown', why: 'Loading the scanner board at the Sim playhead.' };
    if (replay.status === 'error') {
      return { state: 'unknown', why: `The scanner board at the Sim playhead did not load${replay.error ? `: ${replay.error}` : '.'}` };
    }
  }
  const sym = symbol.trim().toUpperCase();
  const ranks: ListRank[] = [];
  for (const { list, label, key } of LISTS) {
    const rows = feed[key] as readonly { symbol: string }[] | undefined;
    if (!rows?.length) continue;
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
