/**
 * Owner of the HOD Momo strip's persisted layout (rows + folded), one
 * versioned localStorage blob. See hodMomoStripConstants.ts for the contract.
 */
import {
  HOD_MOMO_STRIP_DEFAULT_FOLDED,
  HOD_MOMO_STRIP_DEFAULT_ROWS,
  HOD_MOMO_STRIP_MAX_ROWS,
  HOD_MOMO_STRIP_MAX_SHARE,
  HOD_MOMO_STRIP_MIN_ROWS,
  HOD_MOMO_STRIP_ROW_PX,
  HOD_MOMO_STRIP_SCHEMA_VERSION,
  HOD_MOMO_STRIP_STORAGE_KEY,
} from './hodMomoStripConstants';

export type HodMomoStripLayout = {
  rows: number;
  folded: boolean;
};

export const HOD_MOMO_STRIP_DEFAULT_LAYOUT: HodMomoStripLayout = {
  rows: HOD_MOMO_STRIP_DEFAULT_ROWS,
  folded: HOD_MOMO_STRIP_DEFAULT_FOLDED,
};

/** Whole rows between the floor and `maxRows` (defaults to the hard ceiling). */
export function clampStripRows(rows: number, maxRows: number = HOD_MOMO_STRIP_MAX_ROWS): number {
  if (!Number.isFinite(rows)) return HOD_MOMO_STRIP_DEFAULT_ROWS;
  const ceiling = Math.max(HOD_MOMO_STRIP_MIN_ROWS, Math.min(HOD_MOMO_STRIP_MAX_ROWS, Math.floor(maxRows)));
  return Math.min(ceiling, Math.max(HOD_MOMO_STRIP_MIN_ROWS, Math.round(rows)));
}

/** Largest row count that fits in `share` of the content column. */
export function stripMaxRowsFor(contentHeightPx: number, share: number = HOD_MOMO_STRIP_MAX_SHARE): number {
  if (!Number.isFinite(contentHeightPx) || contentHeightPx <= 0) return HOD_MOMO_STRIP_MAX_ROWS;
  return Math.max(HOD_MOMO_STRIP_MIN_ROWS, Math.floor((contentHeightPx * share) / HOD_MOMO_STRIP_ROW_PX));
}

/** Snap a dragged pixel height to whole rows. */
export function snapStripRows(px: number, maxRows: number): number {
  return clampStripRows(px / HOD_MOMO_STRIP_ROW_PX, maxRows);
}

export function stripRowsToPx(rows: number): number {
  return rows * HOD_MOMO_STRIP_ROW_PX;
}

function parseLayout(raw: unknown): HodMomoStripLayout | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const rec = raw as Record<string, unknown>;
  if (Number(rec.schema_version) !== HOD_MOMO_STRIP_SCHEMA_VERSION) {
    console.warn(
      `HOD Momo strip: unknown schema_version ${String(rec.schema_version)} in ${HOD_MOMO_STRIP_STORAGE_KEY}; using defaults`,
    );
    return null;
  }
  const rows = typeof rec.rows === 'number' ? clampStripRows(rec.rows) : HOD_MOMO_STRIP_DEFAULT_ROWS;
  const folded = typeof rec.folded === 'boolean' ? rec.folded : HOD_MOMO_STRIP_DEFAULT_FOLDED;
  return { rows, folded };
}

export function readStripLayout(storage: Pick<Storage, 'getItem'> = localStorage): HodMomoStripLayout {
  try {
    const raw = storage.getItem(HOD_MOMO_STRIP_STORAGE_KEY);
    if (raw == null) return { ...HOD_MOMO_STRIP_DEFAULT_LAYOUT };
    return parseLayout(JSON.parse(raw)) ?? { ...HOD_MOMO_STRIP_DEFAULT_LAYOUT };
  } catch {
    return { ...HOD_MOMO_STRIP_DEFAULT_LAYOUT };
  }
}

export function writeStripLayout(
  layout: HodMomoStripLayout,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(
      HOD_MOMO_STRIP_STORAGE_KEY,
      JSON.stringify({
        schema_version: HOD_MOMO_STRIP_SCHEMA_VERSION,
        rows: clampStripRows(layout.rows),
        folded: Boolean(layout.folded),
      }),
    );
  } catch {
    /* private mode */
  }
}
