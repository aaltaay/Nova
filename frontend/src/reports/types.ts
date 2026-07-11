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
