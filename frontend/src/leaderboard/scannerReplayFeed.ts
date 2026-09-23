/**
 * Pure: the live scanner feed with its five tables swapped for the board at
 * the Sim playhead. Everything else stays the live feed's -- the global bar
 * still states the live connection honestly -- except what would decorate a
 * past row with today's live state: price flashes, per-row quote ages and
 * today's catalysts (live-only, never recorded per minute).
 */
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import type { ScannerReplay } from './leaderboardTypes';

export interface ReplayableFeed {
  gappers: ScannerRow[];
  gainers: ScannerRow[];
  losers: ScannerRow[];
  afterhours: ScannerRow[];
  largeCap: ScannerRow[];
  catalysts: Catalyst[];
  flashSymbols: Record<string, 'up' | 'down'>;
  rowQuoteTs: Record<string, number>;
  replay?: ScannerReplay | null;
}

const NO_CATALYSTS: Catalyst[] = [];
const NO_FLASH: Record<string, 'up' | 'down'> = {};
const NO_QUOTE_TS: Record<string, number> = {};

export function withScannerReplay<T extends ReplayableFeed>(feed: T, replay: ScannerReplay | null): T {
  if (!replay) return feed.replay == null ? feed : { ...feed, replay: null };
  return {
    ...feed,
    gappers: replay.tables.gappers,
    gainers: replay.tables.gainers,
    losers: replay.tables.losers,
    afterhours: replay.tables.afterhours,
    largeCap: replay.tables.largeCap,
    catalysts: NO_CATALYSTS,
    flashSymbols: NO_FLASH,
    rowQuoteTs: NO_QUOTE_TS,
    replay,
  };
}
