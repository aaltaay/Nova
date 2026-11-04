/**
 * Whose trades the Reports tab reads (ADR 069 decision 6, architecture/schema/journal.md). Pure.
 *
 * The tab follows the Account page's venue and its All / You / Bots pick (mockup reports-v1): Paper reads
 * Paper's round trips, one per holder, narrowed to the view, with yours and the bots' beside each total on All.
 * Live and Sim read the journal as it was -- IBKR round trips and imported files, every one yours.
 */
import type { BotCounts, OwnerView } from '../account';
import type { DeskVenue } from '../constantGroups/desk_venue';
import type { BookSums, BooksSplit, ReportsHolder } from './types';

/** What the Account page hands its Reports tab. */
export interface ReportsHost {
  venue: DeskVenue;
  view: OwnerView;
  /** The Bots menu's counts for the year shown (Paper); null off Paper. */
  onBotCounts?: (counts: BotCounts | null) => void;
}

/** Paper is the only venue with two books. */
export const readsBooks = (venue: DeskVenue | null | undefined): boolean => venue === 'paper';

/** The journal query for the venue and the view: none on Live and Sim, `venue=paper` and the pick on Paper. */
export function journalViewQuery(venue: DeskVenue | null | undefined, view: OwnerView | null | undefined): string {
  if (!readsBooks(venue)) return '';
  const params = new URLSearchParams({ venue: 'paper' });
  if (view?.book === 'you') params.set('owner', 'you');
  if (view?.book === 'bots') {
    params.set('owner', 'bots');
    if (view.bot) params.set('bot', view.bot);
  }
  return params.toString();
}

/** The Bots menu's counts from the year's holders: each bot's closed trades, and every bot's together. */
export function botCounts(holders: ReportsHolder[] | null | undefined): BotCounts | null {
  if (!holders) return null;
  const byBot: Record<string, number> = {};
  let all = 0;
  for (const holder of holders) {
    if (holder.owner !== 'bots' || !holder.bot) continue;
    byBot[holder.bot] = (byBot[holder.bot] ?? 0) + holder.trade_count;
    all += holder.trade_count;
  }
  return { all, byBot };
}

/** One book's figure beside a total: its words and the value its colour follows (null: no colour). */
export interface SplitFigure {
  text: string;
  value: number | null;
}

/** Yours and the bots'; a book with no trade there is null, drawn as a dash. */
export type FigureSplit = BooksSplit<SplitFigure | null>;

/** Each book's P&L in `fmt`. */
export function pnlSplit(split: BooksSplit<BookSums> | undefined, fmt: (v: number) => string): FigureSplit | null {
  if (!split) return null;
  const one = (sums: BookSums): SplitFigure | null =>
    sums.trade_count > 0 ? { text: fmt(sums.pnl), value: sums.pnl } : null;
  return { you: one(split.you), bots: one(split.bots) };
}

/** Each book's trade count. */
export function countSplit(split: BooksSplit<BookSums> | undefined): FigureSplit | null {
  if (!split) return null;
  const one = (sums: BookSums): SplitFigure | null =>
    sums.trade_count > 0 ? { text: sums.trade_count.toLocaleString('en-US'), value: null } : null;
  return { you: one(split.you), bots: one(split.bots) };
}

/** Any per-book figure, `pick` returning its words (null: a dash) and its colour value. */
export function figureSplit<T>(split: BooksSplit<T> | undefined, pick: (book: T) => SplitFigure | null): FigureSplit | null {
  return split ? { you: pick(split.you), bots: pick(split.bots) } : null;
}

/** The split in words, for a tooltip: "yours -$295, the bots' —". */
export function splitWords(split: FigureSplit | null): string {
  if (!split) return '';
  return `yours ${split.you?.text ?? '—'}, the bots' ${split.bots?.text ?? '—'}`;
}
