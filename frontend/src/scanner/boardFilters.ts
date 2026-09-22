/**
 * Board filter chips as pure predicates over scanner rows.
 *
 * Every predicate fails OPEN on an unknown fact (single-market-data-feed.mdc:
 * a client-side filter must never drop a row because a metadata field is
 * unknown), and the caller always shows the hidden count -- see
 * ScannerBoardFooter. `halted` is not a row fact yet, so it never filters.
 */
import {
  SCANNER_CHIP_FLOAT_MAX_SHARES,
  SCANNER_CHIP_GAP_MIN_PCT,
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_RELVOL_MIN,
  SCANNER_CHIP_UNAVAILABLE,
  type ScannerChipId,
} from '../constantGroups/scanner_board';
import type { ScannerRow } from '../types/scanner';

export type ChipRow = Pick<ScannerRow, 'gap_percent' | 'float' | 'rel_volume' | 'has_news'>;

export function isChipId(value: unknown): value is ScannerChipId {
  return typeof value === 'string' && (SCANNER_CHIP_IDS as readonly string[]).includes(value);
}

export function isChipAvailable(id: ScannerChipId): boolean {
  return !SCANNER_CHIP_UNAVAILABLE.includes(id);
}

/** One chip, one row. Unknown facts pass. */
export function chipPasses(id: ScannerChipId, row: ChipRow): boolean {
  switch (id) {
    case 'gap':
      return row.gap_percent == null || row.gap_percent * 100 >= SCANNER_CHIP_GAP_MIN_PCT;
    case 'float':
      return row.float == null || row.float <= SCANNER_CHIP_FLOAT_MAX_SHARES;
    case 'relvol':
      return row.rel_volume == null || row.rel_volume >= SCANNER_CHIP_RELVOL_MIN;
    case 'news':
      return row.has_news === true;
    case 'halted':
      // Not a row fact -- never filters (stated in the chip's title).
      return true;
    default:
      return true;
  }
}

export function applyBoardChips<T extends ChipRow>(rows: readonly T[], active: ReadonlySet<ScannerChipId>): T[] {
  if (active.size === 0) return [...rows];
  const ids = [...active].filter(isChipAvailable);
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
