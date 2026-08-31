/** Earnings calendar tab -- Finnhub calendar dates + EPS/revenue estimates,
 * decorated with company name/sector/market cap from the yfinance cache
 * (backend/earnings_calendar.py). No implied move / IV -- not computed. */

export type EarningsSession = 'bmo' | 'amc' | 'intraday';
export type EarningsRange = 'today' | 'tomorrow' | 'week' | 'month';

export interface EarningsRow {
  symbol: string;
  date: string;
  session: EarningsSession;
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  quarter: number | null;
  year: number | null;
  company_name: string | null;
  sector: string | null;
  market_cap: number | null;
}

export interface EarningsDay {
  date: string;
  label: string;
  count: number;
  bmo: EarningsRow[];
  amc: EarningsRow[];
  intraday: EarningsRow[];
}

export interface EarningsView {
  rev: string;
  range: EarningsRange;
  as_of: number;
  error: string | null;
  days: EarningsDay[];
}
