/**
 * A pane's Ahead answer (ADR 065). While `enabled` (the switch on, a mounted 1-minute pane on the visible tab) the
 * pane holds the symbol's one shared poller (`aheadPoller.ts`); while it is off nothing is asked at all. The desk
 * clock the poller rolls its minute on is the Sim playhead on a replay desk, else the wall clock.
 */
import { useEffect, useMemo } from 'react';
import { useSimReplayDesk, useSimReplayPlayhead } from '../sim';
import { acquireAheadPoller, setAheadDeskPlayhead } from './aheadPoller';
import { useAheadHeld } from './aheadStore';
import type { AheadAnswer } from './aheadTypes';

export interface AheadAnswerView {
  answer: AheadAnswer | null;
  /** Words when the last read failed (404 before an API restart, an unreachable API); null otherwise. */
  fetchProblem: string | null;
}

const NONE: AheadAnswerView = { answer: null, fetchProblem: null };

export function useAheadAnswer(symbol: string, enabled: boolean): AheadAnswerView {
  const replay = useSimReplayDesk();
  const playhead = useSimReplayPlayhead();
  useEffect(() => {
    setAheadDeskPlayhead(replay ? playhead : null);
  }, [replay, playhead]);
  useEffect(() => (enabled && symbol ? acquireAheadPoller(symbol) : undefined), [symbol, enabled]);
  const held = useAheadHeld(symbol);
  return useMemo(
    () => (enabled ? { answer: held.answer, fetchProblem: held.problem } : NONE),
    [enabled, held.answer, held.problem],
  );
}
