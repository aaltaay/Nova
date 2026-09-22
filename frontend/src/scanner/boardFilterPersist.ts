/**
 * Owner of the board chips' persisted state: the active chips and the named
 * sets, one prefStore envelope (schema_version) under
 * SCANNER_BOARD_FILTERS_STORAGE_KEY.
 */
import {
  SCANNER_BOARD_FILTERS_STORAGE_KEY,
  SCANNER_SAVED_MAX_SETS,
  type ScannerChipId,
} from '../constantGroups/scanner_board';
import { readPref, writePref } from '../utils/prefStore';
import { isChipId } from './boardFilters';

export type SavedChipSet = { name: string; chips: ScannerChipId[] };

export type BoardFilterState = {
  active: ScannerChipId[];
  sets: SavedChipSet[];
};

export const EMPTY_BOARD_FILTER_STATE: BoardFilterState = { active: [], sets: [] };

function parseChips(raw: unknown): ScannerChipId[] | null {
  if (!Array.isArray(raw)) return null;
  const out: ScannerChipId[] = [];
  for (const id of raw) {
    if (isChipId(id) && !out.includes(id)) out.push(id);
  }
  return out;
}

export function parseBoardFilterState(raw: unknown): BoardFilterState | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const rec = raw as Record<string, unknown>;
  const active = parseChips(rec.active) ?? [];
  const sets: SavedChipSet[] = [];
  if (Array.isArray(rec.sets)) {
    for (const item of rec.sets) {
      if (!item || typeof item !== 'object') continue;
      const { name, chips } = item as Record<string, unknown>;
      const parsed = parseChips(chips);
      if (typeof name !== 'string' || !name.trim() || !parsed) continue;
      if (sets.some((s) => s.name === name.trim())) continue;
      sets.push({ name: name.trim(), chips: parsed });
      if (sets.length >= SCANNER_SAVED_MAX_SETS) break;
    }
  }
  return { active, sets };
}

export function readBoardFilterState(
  storage: Pick<Storage, 'getItem'> = localStorage,
): BoardFilterState {
  return readPref(SCANNER_BOARD_FILTERS_STORAGE_KEY, EMPTY_BOARD_FILTER_STATE, parseBoardFilterState, storage);
}

export function writeBoardFilterState(
  state: BoardFilterState,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  writePref(SCANNER_BOARD_FILTERS_STORAGE_KEY, state, storage);
}

/** Add or replace a named set (name is trimmed; newest kept within the cap). */
export function upsertSavedSet(sets: readonly SavedChipSet[], name: string, chips: ScannerChipId[]): SavedChipSet[] {
  const clean = name.trim();
  if (!clean) return [...sets];
  const rest = sets.filter((s) => s.name !== clean);
  return [...rest, { name: clean, chips: [...chips] }].slice(-SCANNER_SAVED_MAX_SETS);
}

export function removeSavedSet(sets: readonly SavedChipSet[], name: string): SavedChipSet[] {
  return sets.filter((s) => s.name !== name);
}
