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
import type { TickerDetail } from '../types/ticker';
import {
  captureQuoteDetail,
  historicalQuoteDetail,
  replayAssetInfo,
  replayCompanyFacts,
  replayFactsNoteForDetail,
  simEmptyQuoteDetail,
  splitDate,
} from './historicalQuoteDetail';
import type { SimClockState } from './simClockTypes';
import { simRailNote } from './simReplayTarget';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import { isReplayDesk } from './useSimReplayDesk';

export { replayAssetInfo, replayCompanyFacts, splitDate };

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
  const day = clock?.session_date ?? null;
  let view = detail;
  if (loaded && clock?.replay_source === 'historical' && historical?.active) {
    view = historicalQuoteDetail(detail, historical, day);
  } else if (loaded && clock?.replay_source === 'capture' && clock) {
    view = captureQuoteDetail(detail, clock, sym);
  } else if (simRailNote(sym, clock, sim)) {
    view = simEmptyQuoteDetail(detail, sym, day);
  }
  if (!replayDesk || !day) return { detail: view, note: null };
  return {
    detail: {
      ...view,
      asset: replayAssetInfo(view.asset),
      listing: null,
      fundamentals: replayCompanyFacts(detail.fundamentals, day),
    },
    note: replayFactsNoteForDetail(detail, sym, day),
  };
}
