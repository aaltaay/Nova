/**
 * Whose trades the Reports tab reads (ADR 072, architecture/schema/journal.md). Pure.
 *
 * The tab follows the Account page's venue and its All / You / Claude / The brain / Earlier bots pick (mockup
 * three-books v1, "Account › Reports"): Paper reads Paper's round trips, one per holder, narrowed to the pick, with
 * each of the four books beside each total on All. Live and Sim read the journal as it was -- IBKR round trips and
 * imported files, every one yours (Sim's trades never reach the journal).
 */
import type { BotCounts, OwnerView } from '../account';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { OWNERS, OWNER_NAMES, type Owner } from '../constantGroups/owners';
import type { BookSums, BooksSplit, ReportsHolder } from './types';

/** What the Account page hands its Reports tab. */
export interface ReportsHost {
  venue: DeskVenue;
  view: OwnerView;
  /** The switch's counts for the year shown (Paper); null off Paper. */
  onBotCounts?: (counts: BotCounts | null) => void;
}

/** Paper is the only venue whose journal keeps the books. */
export const readsBooks = (venue: DeskVenue | null | undefined): boolean => venue === 'paper';

const isOwner = (book: string | null | undefined): book is Owner => OWNERS.includes(book as Owner);

/** The journal query: none on Live and Sim; on Paper `venue=paper`, the pick's `owner`, and `bot` for one earlier bot. */
export function journalViewQuery(venue: DeskVenue | null | undefined, view: OwnerView | null | undefined): string {
  if (!readsBooks(venue)) return '';
  const params = new URLSearchParams({ venue: 'paper' });
  if (isOwner(view?.book)) {
    params.set('owner', view.book);
    if (view.book === 'earlier_bots' && view.bot) params.set('bot', view.bot);
  }
  return params.toString();
}

/**
 * The switch's counts from the year's holders: each book's closed trades (a book with none counts 0), and inside
 * Earlier bots each retired bot's and every one's together.
 */
export function botCounts(holders: ReportsHolder[] | null | undefined): BotCounts | null {
  if (!holders) return null;
  const books: Record<Owner, number> = { you: 0, claude: 0, brain: 0, earlier_bots: 0 };
  const byBot: Record<string, number> = {};
  for (const holder of holders) {
    if (!isOwner(holder.owner)) continue;
    books[holder.owner] += holder.trade_count;
    if (holder.owner === 'earlier_bots' && holder.bot) byBot[holder.bot] = (byBot[holder.bot] ?? 0) + holder.trade_count;
  }
  return { all: books.earlier_bots, byBot, books };
}

/** One book's figure beside a total: its words and the value its colour follows (null: no colour). */
export interface SplitFigure {
  text: string;
  value: number | null;
}

/** Each book's figure; null is a book the answer did not carry, or one with no figure there, drawn as a dash. */
export type FigureSplit = BooksSplit<SplitFigure | null>;

const eachBook = <T>(split: BooksSplit<T>, pick: (book: T) => SplitFigure | null): FigureSplit => {
  const out = {} as FigureSplit;
  for (const owner of OWNERS) out[owner] = split[owner] == null ? null : pick(split[owner]);
  return out;
};

/** Each book's P&L in `fmt`: a total lists all four, a book with no trade there at its $0. */
export function pnlSplit(split: BooksSplit<BookSums> | undefined, fmt: (v: number) => string): FigureSplit | null {
  return split ? eachBook(split, (sums) => ({ text: fmt(sums.pnl), value: sums.pnl })) : null;
}

/** Each book's trade count, 0 included. */
export function countSplit(split: BooksSplit<BookSums> | undefined): FigureSplit | null {
  return split ? eachBook(split, (sums) => ({ text: sums.trade_count.toLocaleString('en-US'), value: null })) : null;
}

/** Any per-book figure, `pick` returning its words (null: a dash) and its colour value. */
export function figureSplit<T>(split: BooksSplit<T> | undefined, pick: (book: T) => SplitFigure | null): FigureSplit | null {
  return split ? eachBook(split, pick) : null;
}

/** The books that closed a trade there, in order: a day lists only these (mockup three-books v1). */
export function tradedBooks(split: BooksSplit<BookSums> | undefined): Owner[] {
  return split ? OWNERS.filter((owner) => (split[owner]?.trade_count ?? 0) > 0) : [];
}

/** The split in words, for a tooltip: "You -$295, Claude $0, The brain $0, Earlier bots $30". */
export function splitWords(split: FigureSplit | null, books: readonly Owner[] = OWNERS): string {
  if (!split) return '';
  return books.map((owner) => `${OWNER_NAMES[owner]} ${split[owner]?.text ?? '—'}`).join(', ');
}
