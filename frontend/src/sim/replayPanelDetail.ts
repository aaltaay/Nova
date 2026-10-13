/**
 * The scanner quote panel's detail on a Sim desk (operator report, 2026-10-12): what was known at
 * the playhead, or a stated absence -- never today's live values styled as the replayed day's.
 *
 * - The loaded replay's own symbol shows the replay's quote at the playhead, as the Trader does: a
 *   historical window's snapshot (`historicalQuoteDetail`), a Session Record's quote
 *   (`captureQuoteDetail`). Any other symbol, or a replay not read yet, gets the empty quote.
 * - Company facts: Nova holds only today's (Yahoo's latest), so every share count, price range,
 *   ratio and date is left out off the live edge and the panel says so. On a Jul 15 GRML replay the
 *   panel showed today's 3.08M float, smaller than that day's by GRML's 1:50 split of Aug 24. Who
 *   the company is (sector, industry, country) stays, and so does a split on or before the day.
 */
import type { FundamentalsData, TickerDetail } from '../types/ticker';
import { captureQuoteDetail, historicalQuoteDetail, simEmptyQuoteDetail } from './historicalQuoteDetail';
import { simReplayFactsNote } from './simConstants';
import type { SimClockState } from './simClockTypes';
import { simRailNote } from './simReplayTarget';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import { isReplayDesk } from './useSimReplayDesk';

const SPLIT_DATE = /\((\d{4}-\d{2}-\d{2})\)/;

/** The split's date in `recent_split` ("1:50 (2026-08-24)"), or null when it names none. */
export function splitDate(recentSplit: string | null | undefined): string | null {
  return SPLIT_DATE.exec(recentSplit ?? '')?.[1] ?? null;
}

/** The company facts a past session can show: who the company is, and a split by that day. */
export function replayCompanyFacts(f: FundamentalsData | null, sessionDate: string): FundamentalsData | null {
  if (!f) return null;
  const split = splitDate(f.recent_split);
  return {
    country: f.country ?? null,
    country_code: f.country_code ?? null,
    sector: f.sector,
    industry: f.industry,
    recent_split: split != null && split <= sessionDate ? f.recent_split : null,
    market_cap: null,
    shares_outstanding: null,
    float_shares: null,
    held_percent_insiders: null,
    float_contradicted: null,
    float_contradicted_reason: null,
    shares_issued: null,
    shares_issued_reason: null,
    short_interest: null,
    short_interest_ts: null,
    short_above_float: null,
    short_above_float_reason: null,
    short_ratio: null,
    short_percent_of_float: null,
    pe_ratio: null,
    forward_pe: null,
    eps: null,
    fifty_two_week_high: null,
    fifty_two_week_low: null,
    dividend_yield: null,
    beta: null,
    earnings_date: null,
  };
}

export interface ReplayPanelDetail {
  detail: TickerDetail | null;
  /** What the panel leaves out off the live edge, and why; null on a live desk. */
  note: string | null;
}

export function replayPanelDetail(
  detail: TickerDetail | null,
  symbol: string,
  clock: SimClockState | null | undefined,
  sim: boolean,
  historical: HistoricalSnapshot | null | undefined,
): ReplayPanelDetail {
  const sym = symbol.trim().toUpperCase();
  if (!detail || !sim) return { detail, note: null };
  const replayDesk = isReplayDesk(sim, clock);
  const loaded = replayDesk && (clock?.replay_symbol ?? '').trim().toUpperCase() === sym;
  let view = detail;
  if (loaded && clock?.replay_source === 'historical' && historical?.active) {
    view = historicalQuoteDetail(detail, historical);
  } else if (loaded && clock?.replay_source === 'capture' && clock) {
    view = captureQuoteDetail(detail, clock, sym);
  } else if (simRailNote(sym, clock, sim)) {
    view = simEmptyQuoteDetail(detail, sym);
  }
  if (!replayDesk || !clock?.session_date) return { detail: view, note: null };
  const day = clock.session_date;
  const split = splitDate(detail.fundamentals?.recent_split);
  const later = split != null && split > day ? `${sym} split ${detail.fundamentals?.recent_split}` : null;
  return {
    detail: { ...view, fundamentals: replayCompanyFacts(view.fundamentals, day) },
    note: simReplayFactsNote(day, later),
  };
}
