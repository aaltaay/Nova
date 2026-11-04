/** What the Reports tab says about whose trades it shows (ADR 069 decision 6, mockup reports-v1). Feature-local. */

/** Paper's calendar reads its own round trips (mockup item 2). */
export const REPORTS_SOURCE_NOTE_PAPER =
  "Paper's trades: one round trip per holder, closed from the practice ledger at its own cost — the Account page's split. Live and imported trades are on Live.";
/** Import file is Live's: an import never lands in Paper's trades (mockup item 12). */
export const REPORTS_IMPORT_ON_LIVE =
  "Import file is on Live: imported trades are yours, and they count with Live's, never in Paper's.";
export const reportsEmptyPaper = (year: number): string => `No closed Paper trades in ${year}.`;

/** The two books beside each total. */
export const REPORTS_SPLIT_YOU = 'Yours';
export const REPORTS_SPLIT_BOTS = "The bots'";

/** Tag performance on Paper (mockup item 6). */
export const REPORTS_TAGS_TITLE = 'Tag performance';
export const REPORTS_TAGS_EMPTY_PAPER = 'No tagged trades yet.';
export const REPORTS_TAGS_PAPER_HINT =
  "Paper's trades carry no tags (none of its orders is tagged). Once one is, its row counts only the trades the switch shows: All, You, or the bots.";

/** Where a Paper trade's stop comes from, and how many of each book's sent none (mockup item 7). */
export const REPORTS_R_PAPER_STOP = "A Paper trade's stop is the stop order sent with its entry";
export const reportsRPaperStops = (you: { skipped: number; n: number }, bots: { skipped: number; n: number }): string =>
  `${REPORTS_R_PAPER_STOP}: ${you.skipped} of your ${you.n} sent none, and ${bots.skipped} of the bots' ${bots.n}.`;

/** The drawdown chart on Paper (mockup item 8). */
export const REPORTS_DRAWDOWN_PAPER_HINT =
  'One bar per closed trade, in close order: the running P&L, coloured by whose trade it was, and drawn from its lowest point to its highest.';
