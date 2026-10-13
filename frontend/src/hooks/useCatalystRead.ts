/**
 * One Catalyst cell's read (`whyBatchStore`): the symbol's row on `board` (null: no board, the Trader card's
 * read). The sample desk reads nothing live, and an API from before the batch route is `unavailable`: the cell
 * then shows the news mark it showed as the News column.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useSimReplayPlayhead } from '../sim';
import { catalystKey, whyBatchStore, type CatalystReadState } from './whyBatchStore';

export interface CatalystRead extends CatalystReadState {
  unavailable: boolean;
}

const OFF: CatalystReadState = Object.freeze({ read: null, loading: false, error: null });
const noSubscription = () => () => {};

export function useCatalystRead(symbol: string, board: string | null, enabled = true): CatalystRead {
  const sample = useSampleDataOptional();
  const off = !!sample || !enabled || !symbol.trim();
  const key = catalystKey(symbol, board);
  const subscribe = useCallback(
    (listener: () => void) => (off ? noSubscription() : whyBatchStore.subscribe(key, listener)),
    [key, off],
  );
  const state = useSyncExternalStore(subscribe, () => (off ? OFF : whyBatchStore.getSnapshot(key)));
  const unavailable = useSyncExternalStore(whyBatchStore.subscribeUnavailable, whyBatchStore.isUnavailable);
  return { ...state, unavailable: off || unavailable };
}

/** Rendered once per table: hands the Sim replay's playhead to the store (a rewind reads every cell again). */
export function CatalystPlayheadSync(): null {
  const playhead = useSimReplayPlayhead();
  useEffect(() => { whyBatchStore.setPlayhead(playhead); }, [playhead]);
  return null;
}
