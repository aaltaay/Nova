/**
 * Board chip state + named sets for the Scanner board header. Toggling a
 * chip recomputes the rows the page passes through `filterRows`; every
 * change is written back through boardFilterPersist.
 */
import { useCallback, useMemo, useState } from 'react';
import type { ScannerChipId } from '../constantGroups/scanner_board';
import { SCANNER_SAVED_CUSTOM, SCANNER_SAVED_NONE } from '../constantGroups/scanner_board';
import {
  readBoardFilterState,
  removeSavedSet,
  upsertSavedSet,
  writeBoardFilterState,
  type BoardFilterState,
  type SavedChipSet,
} from './boardFilterPersist';
import { applyBoardChips, chipsInOrder, isChipAvailable, sameChips, type ChipRow } from './boardFilters';

export interface BoardFilters {
  active: ReadonlySet<ScannerChipId>;
  sets: readonly SavedChipSet[];
  /** Name of the saved set the active chips equal, "none" when empty, "custom" otherwise. */
  activeSetName: string;
  toggle: (id: ScannerChipId) => void;
  clear: () => void;
  applySet: (name: string) => void;
  saveCurrentAs: (name: string) => void;
  forgetSet: (name: string) => void;
  filterRows: <T extends ChipRow>(rows: readonly T[]) => T[];
}

export function activeSetNameFor(active: ReadonlySet<ScannerChipId>, sets: readonly SavedChipSet[]): string {
  if (active.size === 0) return SCANNER_SAVED_NONE;
  const match = sets.find((s) => sameChips(active, s.chips));
  return match ? match.name : SCANNER_SAVED_CUSTOM;
}

export function useBoardFilters(): BoardFilters {
  const [state, setState] = useState<BoardFilterState>(readBoardFilterState);
  const active = useMemo(() => new Set(state.active), [state.active]);

  const update = useCallback((patch: (prev: BoardFilterState) => BoardFilterState) => {
    setState((prev) => {
      const next = patch(prev);
      writeBoardFilterState(next);
      return next;
    });
  }, []);

  const toggle = useCallback((id: ScannerChipId) => {
    if (!isChipAvailable(id)) return;
    update((prev) => {
      const set = new Set(prev.active);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      return { ...prev, active: chipsInOrder(set) };
    });
  }, [update]);

  const clear = useCallback(() => update((prev) => ({ ...prev, active: [] })), [update]);

  const applySet = useCallback((name: string) => {
    update((prev) => {
      const found = prev.sets.find((s) => s.name === name);
      return found ? { ...prev, active: [...found.chips] } : prev;
    });
  }, [update]);

  const saveCurrentAs = useCallback((name: string) => {
    update((prev) => ({ ...prev, sets: upsertSavedSet(prev.sets, name, prev.active) }));
  }, [update]);

  const forgetSet = useCallback((name: string) => {
    update((prev) => ({ ...prev, sets: removeSavedSet(prev.sets, name) }));
  }, [update]);

  const filterRows = useCallback(
    <T extends ChipRow>(rows: readonly T[]): T[] => applyBoardChips(rows, active),
    [active],
  );

  const sets = state.sets;
  return useMemo(
    () => ({
      active,
      sets,
      activeSetName: activeSetNameFor(active, sets),
      toggle,
      clear,
      applySet,
      saveCurrentAs,
      forgetSet,
      filterRows,
    }),
    [active, sets, toggle, clear, applySet, saveCurrentAs, forgetSet, filterRows],
  );
}
