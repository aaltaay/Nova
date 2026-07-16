/** Types for GET /api/journal/calendar — mirrors backend/journal/calendar.py */

export type DayResult = 'win' | 'loss' | 'flat';

export interface CalendarDay {
  date: string;
  pnl: number;
  trade_count: number;
  result: DayResult;
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
}

export interface CalendarWeekTotal {
  week_index: number;
  pnl: number;
  trade_count: number;
  days: string[];
}

export interface YearCalendarResponse {
  year: number;
  timezone: string;
  includes_mock_data: boolean;
  year_pnl: number;
  year_trade_count: number;
  winning_days: number;
  losing_days: number;
  flat_days: number;
  best_day: { date: string; pnl: number; trade_count: number } | null;
  worst_day: { date: string; pnl: number; trade_count: number } | null;
  months: CalendarMonthSummary[];
}

export interface MonthCalendarResponse extends CalendarMonthSummary {
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

export interface TagsResponse {
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

export interface RMultiplesResponse {
  includes_mock_data: boolean;
  trade_count: number;
  scored_count: number;
  skipped_no_stop: number;
  expectancy_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  trades: RMultipleTradeRow[];
}

/** GET /api/journal/drawdown */
export interface DrawdownCurvePoint {
  trade_id: number | null;
  symbol: string;
  closed_ts: number;
  pnl: number;
  equity: number;
  drawdown: number;
}

export interface DrawdownResponse {
  includes_mock_data: boolean;
  trade_count: number;
  final_equity: number;
  peak_equity: number;
  max_drawdown: number;
  max_drawdown_pct: number | null;
  curve: DrawdownCurvePoint[];
}
