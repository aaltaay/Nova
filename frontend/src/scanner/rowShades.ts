/**
 * Row shades on the Scanner lists (operator approved 2026-10-26): one rule for every list that draws scanner rows
 * -- Gappers, Gainers, Losers, After Hours, live or played back -- so a stock reads the same wherever it shows.
 *
 *   float   under 10M the brightest shade, 10-20M the second, above it none;
 *   volume  a shade that deepens with the shares traded up to 1M, then stays the same (5 steps);
 *   row     the whole row lit when the float is under 10M and the day relative volume is 5x or more.
 *
 * Thresholds live in ``constantGroups/scanner_board.ts``. An unknown figure is never shaded: no colour reads as
 * "not known", never as a value. A float the row itself doubts (Yahoo's counts contradict it, or an SEC filing says
 * shares were issued since: the "?" mark) is not shaded either, so a doubtful figure never looks certain. The news
 * flame's heat (fresher news, hotter flame) is ``NewsCell``'s, unchanged.
 */
import {
  SCANNER_SHADE_FLOAT_LOW_MAX,
  SCANNER_SHADE_FLOAT_MID_MAX,
  SCANNER_SHADE_HOT_RVOL_MIN,
  SCANNER_SHADE_SKIP_BOARDS,
  SCANNER_SHADE_VOLUME_FULL,
  SCANNER_SHADE_VOLUME_STEPS,
} from '../constantGroups/scanner_board';
import type { ScannerRow } from '../types/scanner';
import { dayRelVolume } from './boardFilters';

export type FloatShade = 'low' | 'mid';

export type RowShades = {
  /** The float cell's shade, or null (above 20M, unknown or doubtful). */
  float: FloatShade | null;
  /** The volume cell's shade, 1 (lightest) to ``SCANNER_SHADE_VOLUME_STEPS``, or null (unknown or none traded). */
  volume: number | null;
  /** The whole row lit: a low float and a high day relative volume. */
  hot: boolean;
};

type ShadeRow = Pick<ScannerRow, 'float' | 'volume' | 'rel_volume' | 'rvol_source' | 'float_contradicted'
  | 'shares_issued'>;

const known = (value: number | null | undefined): value is number => value != null && Number.isFinite(value);

export function floatShade(row: Pick<ShadeRow, 'float' | 'float_contradicted' | 'shares_issued'>): FloatShade | null {
  if (!known(row.float) || row.float <= 0 || row.float_contradicted === true || row.shares_issued) return null;
  if (row.float < SCANNER_SHADE_FLOAT_LOW_MAX) return 'low';
  return row.float <= SCANNER_SHADE_FLOAT_MID_MAX ? 'mid' : null;
}

export function volumeShade(volume: number | null | undefined): number | null {
  if (!known(volume) || volume <= 0) return null;
  const steps = Math.ceil((volume / SCANNER_SHADE_VOLUME_FULL) * SCANNER_SHADE_VOLUME_STEPS);
  return Math.max(1, Math.min(SCANNER_SHADE_VOLUME_STEPS, steps));
}

/** Every shade of one row; ``board`` a list that is not shaded (``SCANNER_SHADE_SKIP_BOARDS``) answers none. */
export function rowShades(row: ShadeRow, board?: string | null): RowShades {
  if (board != null && SCANNER_SHADE_SKIP_BOARDS.includes(board)) return { float: null, volume: null, hot: false };
  const float = floatShade(row);
  const rvol = dayRelVolume(row);
  return { float, volume: volumeShade(row.volume), hot: float === 'low' && rvol != null && rvol >= SCANNER_SHADE_HOT_RVOL_MIN };
}
