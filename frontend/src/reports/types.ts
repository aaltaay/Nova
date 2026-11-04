/** Types for GET /api/journal/calendar — mirrors backend/journal/calendar.py */

export type DayResult = 'win' | 'loss' | 'flat';

/**
 * Whose trades a Reports read was (ADR 069 decision 6, architecture/schema/journal.md): the venue and the view
 * every answer echoes, and yours and the bots' beside each total on Paper's All view.
 */
export type JournalVenue = 'live' | 'paper';
export type JournalBook = 'you' | 'bots';

export interface JournalView {
  owner: JournalBook | null;
  bot: string | null;
}

export interface BooksSplit<T> {
  you: T;
  bots: T;
}

export interface BookSums {
  pnl: number;
  trade_count: number;
}

/** A holder with closed trades in the year shown (Paper), whatever the view: the Bots menu's counts. */
export interface ReportsHolder {
  owner: JournalBook;
  bot: string | null;
  trade_count: number;
}

interface ReadBy {
  venue?: JournalVenue;
  view?: JournalView;
}

export interface CalendarDay {
  date: string;
  pnl: number;
  trade_count: number;
  result: DayResult;
  by_owner?: BooksSplit<BookSums>;
}

export interface CalendarMonthSummary {
  year: number;
  month: number;
  pnl: number;
  trade_count: number;
  winning_days: number;
  losing_days: number;
  flat_days: number;
  days: CalendarDay[];
  by_owner?: BooksSplit<BookSums>;
}

export interface CalendarWeekTotal {
  week_index: number;
  pnl: number;
  trade_count: number;
  days: string[];
  by_owner?: BooksSplit<BookSums>;
}

export interface CalendarDayBrief {
  date: string;
  pnl: number;
  trade_count: number;
  by_owner?: BooksSplit<BookSums>;
}

export interface YearCalendarResponse extends ReadBy {
  year: number;
  timezone: string;
  includes_mock_data: boolean;
  year_pnl: number;
  year_trade_count: number;
  winning_days: number;
  losing_days: number;
  flat_days: number;
  best_day: CalendarDayBrief | null;
  worst_day: CalendarDayBrief | null;
  months: CalendarMonthSummary[];
  by_owner?: BooksSplit<BookSums>;
  holders?: ReportsHolder[];
}

export interface MonthCalendarResponse extends CalendarMonthSummary, ReadBy {
  timezone: string;
  includes_mock_data: boolean;
  weeks: CalendarWeekTotal[];
}

/** GET /api/journal/tags */
export interface TagPerformanceRow {
  tag: string;
  count: number;
  wins: number;
  losses: number;
  flat: number;
  win_rate_pct: number | null;
  pnl: number;
}

export interface TagsResponse extends ReadBy {
  includes_mock_data: boolean;
  count: number;
  tags: TagPerformanceRow[];
}

/** GET /api/journal/r-multiples */
export interface RMultipleTradeRow {
  trade_id: number | null;
  symbol: string;
  pnl: number;
  risk_dollars: number | null;
  r_multiple: number | null;
}

export interface RBookSummary {
  trade_count: number;
  scored_count: number;
  skipped_no_stop: number;
  expectancy_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
}

export interface RMultiplesResponse extends RBookSummary, ReadBy {
  includes_mock_data: boolean;
  trades: RMultipleTradeRow[];
  by_owner?: BooksSplit<RBookSummary>;
}

/** GET /api/journal/drawdown */
export interface DrawdownCurvePoint {
  trade_id: number | null;
  symbol: string;
  closed_ts: number;
  pnl: number;
  equity: number;
  drawdown: number;
  /** Whose trade (ADR 069); an older backend sends neither. */
  owner?: JournalBook;
  bot?: string | null;
}

export interface DrawdownBookSummary {
  trade_count: number;
  final_equity: number;
  peak_equity: number;
  max_drawdown: number;
  max_drawdown_pct: number | null;
}

export interface DrawdownResponse extends DrawdownBookSummary, ReadBy {
  includes_mock_data: boolean;
  curve: DrawdownCurvePoint[];
  by_owner?: BooksSplit<DrawdownBookSummary>;
}

/** POST /api/journal/import */
export interface JournalImportResult {
  ok: boolean;
  source?: string | null;
  imported: number;
  duplicates?: number;
  skipped?: number;
  errors?: string[];
  error?: string | null;
}
