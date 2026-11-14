/** What the Reports tab says about whose trades it shows (ADR 072, mockup three-books v1). Feature-local. */
import type { Owner } from '../constantGroups/owners';

/** Paper's calendar reads its own round trips (mockup reports-v1 item 2). */
export const REPORTS_SOURCE_NOTE_PAPER =
  "Paper's trades: one round trip per holder, closed from the practice ledger at its own cost — the Account page's split. Live and imported trades are on Live.";
/** Import file is Live's: an import never lands in Paper's trades (mockup reports-v1 item 12). */
export const REPORTS_IMPORT_ON_LIVE =
  "Import file is on Live: imported trades are yours, and they count with Live's, never in Paper's.";
export const reportsEmptyPaper = (year: number): string => `No closed Paper trades in ${year}.`;

/** Tag performance on Paper (mockup reports-v1 item 6). */
export const REPORTS_TAGS_TITLE = 'Tag performance';
export const REPORTS_TAGS_EMPTY_PAPER = 'No tagged trades yet.';
export const REPORTS_TAGS_PAPER_HINT =
  "Paper's trades carry no tags (none of its orders is tagged). Once one is, its row counts only the trades the switch shows: All, You, Claude, the brain or Earlier bots.";

/** Each book's trades mid-sentence: "your 2", "Claude's 1", "the brain's 0", "the earlier bots' 5". */
const BOOK_OF: Record<Owner, string> = {
  you: 'your', claude: "Claude's", brain: "the brain's", earlier_bots: "the earlier bots'",
};

/** One book's trades and how many of them sent no stop. */
export interface BookStops {
  owner: Owner;
  skipped: number;
  n: number;
}

/** Where a Paper trade's stop comes from, and how many of each book's sent none (mockup reports-v1 item 7). */
export const REPORTS_R_PAPER_STOP = "A Paper trade's stop is the stop order sent with its entry";
export function reportsRPaperStops(books: BookStops[]): string {
  const parts = books.filter((b) => b.n > 0).map((b) => `${b.skipped} of ${BOOK_OF[b.owner]} ${b.n}`);
  if (parts.length === 0) return `${REPORTS_R_PAPER_STOP}.`;
  const last = parts.pop();
  const list = parts.length ? `${parts.join(', ')} and ${last}` : last;
  return `${REPORTS_R_PAPER_STOP}: ${list} sent none.`;
}

/** The drawdown chart on Paper (mockup reports-v1 item 8). */
export const REPORTS_DRAWDOWN_PAPER_HINT =
  'One bar per closed trade, in close order: the running P&L, coloured by whose trade it was, and drawn from its lowest point to its highest.';
