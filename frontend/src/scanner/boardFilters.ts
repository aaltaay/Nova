/**
 * Board filter chips as pure predicates over scanner rows.
 *
 * Every predicate fails OPEN on an unknown fact (single-market-data-feed.mdc:
 * a client-side filter must never drop a row because a metadata field is
 * unknown), and the caller always shows the hidden count -- see
 * ScannerBoardFooter. `halted` is a fact only played-back rows state (ADR
 * 023), so that chip filters only while the board is played back (#487).
 */
import {
  SCANNER_CHIP_FLOAT_MAX_SHARES,
  SCANNER_CHIP_GAP_MIN_PCT,
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_PLAYBACK_ONLY,
  SCANNER_CHIP_RELVOL_MIN,
  type ScannerChipId,
} from '../constantGroups/scanner_board';
import type { ScannerRow } from '../types/scanner';
import { isCompanyNews } from '../utils/catalystVerdict';

export type ChipRow = Pick<
  ScannerRow,
  'gap_percent' | 'float' | 'rel_volume' | 'has_news' | 'news_unknown' | 'rvol_source' | 'catalyst' | 'halted'
>;

/** A Sim playback row's time-of-day RVOL is another basis than the chip's day multiple (ADR 023): unknown here. */
const OTHER_RVOL_BASIS = 'time_of_day_20';

export function isChipId(value: unknown): value is ScannerChipId {
  return typeof value === 'string' && (SCANNER_CHIP_IDS as readonly string[]).includes(value);
}

/** Can this chip filter the board shown? A playback-only chip needs played-back rows. */
export function isChipAvailable(id: ScannerChipId, playback = false): boolean {
  return playback || !SCANNER_CHIP_PLAYBACK_ONLY.includes(id);
}

/** One chip, one row. Unknown facts pass. */
export function chipPasses(id: ScannerChipId, row: ChipRow): boolean {
  switch (id) {
    case 'gap':
      return row.gap_percent == null || row.gap_percent * 100 >= SCANNER_CHIP_GAP_MIN_PCT;
    case 'float':
      return row.float == null || row.float <= SCANNER_CHIP_FLOAT_MAX_SHARES;
    case 'relvol':
      return row.rel_volume == null || row.rvol_source === OTHER_RVOL_BASIS || row.rel_volume >= SCANNER_CHIP_RELVOL_MIN;
    case 'news':
      // A live row with a verdict (ADR 024): company news only -- a movers list or a market wrap
      // naming the ticker is not news about it. A verdict not read yet is unknown, and unknowns pass.
      if (row.catalyst !== undefined) return row.catalyst === null || isCompanyNews(row.catalyst);
      // A played-back row that did not record its news is unknown, and unknowns pass.
      return row.has_news === true || row.news_unknown === true;
    case 'halted':
      // A played-back row states its halt. null -- a rebuilt minute, or the halt feed was not
      // answering -- is unknown, and unknowns pass; only a stated `false` is dropped.
      return row.halted !== false;
    default:
      return true;
  }
}

export function applyBoardChips<T extends ChipRow>(
  rows: readonly T[],
  active: ReadonlySet<ScannerChipId>,
  playback = false,
): T[] {
  if (active.size === 0) return [...rows];
  const ids = [...active].filter((id) => isChipAvailable(id, playback));
  if (ids.length === 0) return [...rows];
  return rows.filter((row) => ids.every((id) => chipPasses(id, row)));
}

/** Stable comparison of two chip sets (order-free). */
export function sameChips(a: ReadonlySet<ScannerChipId>, b: readonly ScannerChipId[]): boolean {
  if (a.size !== b.length) return false;
  return b.every((id) => a.has(id));
}

/** Canonical order for persistence and display. */
export function chipsInOrder(active: ReadonlySet<ScannerChipId>): ScannerChipId[] {
  return SCANNER_CHIP_IDS.filter((id) => active.has(id));
}
