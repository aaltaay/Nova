/**
 * Display-only Time & Sales min-size filter.
 * Does not touch the IBKR tape stream or the hook ring -- only what the
 * virtualized panel paints. Persisted via prefStore (D-017 envelope).
 */
import {
  TAPE_MIN_SIZE_FILTER_MENU_PAD_PX,
  TAPE_MIN_SIZE_STORAGE_KEY,
} from '../constants';
import { readPref, writePref } from '../utils/prefStore';

export function parseTapeMinSize(raw: unknown): number | null {
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    const n = Math.floor(raw);
    return n > 0 ? n : 0;
  }
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (trimmed === '') return 0;
    if (!/^\d+$/.test(trimmed)) return null;
    const n = Number.parseInt(trimmed, 10);
    return n > 0 ? n : 0;
  }
  return null;
}

/** Keep the draft in the box; only commit empty or a whole number. */
export function applyTapeMinSizeDraft(draft: string): number | null {
  return parseTapeMinSize(draft);
}

export function filterTapePrints<T extends { size: number }>(
  prints: readonly T[],
  minSize: number,
): T[] {
  if (minSize <= 0) return prints.slice();
  return prints.filter((print) => print.size >= minSize);
}

export function tapeMinSizeBadgeLabel(minSize: number): string | null {
  if (minSize <= 0) return null;
  return `Size \u2265 ${minSize}`;
}

export function tapeMinSizeEmptyLabel(minSize: number): string {
  const badge = tapeMinSizeBadgeLabel(minSize);
  return badge ? `No prints ${badge}` : 'Waiting for prints…';
}

export function readTapeMinSize(
  storage: Pick<Storage, 'getItem'> = localStorage,
): number {
  return readPref(TAPE_MIN_SIZE_STORAGE_KEY, 0, parseTapeMinSize, storage);
}

export function writeTapeMinSize(
  minSize: number,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  writePref(TAPE_MIN_SIZE_STORAGE_KEY, minSize > 0 ? minSize : 0, storage);
}

export function tapeFilterMenuPosition(input: {
  x: number;
  y: number;
  menuWidth: number;
  menuHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  pad?: number;
}): { top: number; left: number } {
  const pad = input.pad ?? TAPE_MIN_SIZE_FILTER_MENU_PAD_PX;
  const maxLeft = input.viewportWidth - input.menuWidth - pad;
  const maxTop = input.viewportHeight - input.menuHeight - pad;
  const left = input.x + input.menuWidth + pad > input.viewportWidth
    ? Math.max(pad, Math.min(input.x - input.menuWidth, maxLeft))
    : input.x;
  const top = input.y + input.menuHeight + pad > input.viewportHeight
    ? Math.max(pad, maxTop)
    : input.y;
  return { top: Math.max(pad, top), left: Math.max(pad, left) };
}
