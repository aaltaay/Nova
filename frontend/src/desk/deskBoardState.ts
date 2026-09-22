/**
 * Persisted Desk board state: which scanner list the board shows, under one
 * versioned localStorage key. Owner: this module. Invalidation: `v` bump --
 * an older shape is ignored, never migrated by guesswork (persisted-state.mdc).
 */
import { DESK_BOARD_DEFAULT_LIST, DESK_BOARD_STORAGE_KEY } from '../constantGroups/desk';

export const DESK_BOARD_STATE_VERSION = 1;

export interface DeskBoardState {
  v: typeof DESK_BOARD_STATE_VERSION;
  list: string;
}

export const DESK_BOARD_DEFAULT_STATE: DeskBoardState = {
  v: DESK_BOARD_STATE_VERSION,
  list: DESK_BOARD_DEFAULT_LIST,
};

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function readDeskBoardState(
  storage: Pick<Storage, 'getItem'> | null = safeStorage(),
): DeskBoardState {
  try {
    const raw = storage?.getItem(DESK_BOARD_STORAGE_KEY);
    if (!raw) return DESK_BOARD_DEFAULT_STATE;
    const parsed = JSON.parse(raw) as Partial<DeskBoardState> | null;
    if (!parsed || parsed.v !== DESK_BOARD_STATE_VERSION) return DESK_BOARD_DEFAULT_STATE;
    return {
      v: DESK_BOARD_STATE_VERSION,
      list: typeof parsed.list === 'string' && parsed.list ? parsed.list : DESK_BOARD_DEFAULT_LIST,
    };
  } catch {
    return DESK_BOARD_DEFAULT_STATE;
  }
}

export function writeDeskBoardState(
  state: DeskBoardState,
  storage: Pick<Storage, 'setItem'> | null = safeStorage(),
): void {
  try {
    storage?.setItem(DESK_BOARD_STORAGE_KEY, JSON.stringify({ ...state, v: DESK_BOARD_STATE_VERSION }));
  } catch {
    /* private mode: the board still works, it just forgets the list */
  }
}
