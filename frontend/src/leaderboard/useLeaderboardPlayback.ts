/**
 * The Scanner board at the Sim playhead (ADR 023, "one desk, one clock").
 *
 * Null on Live and Paper and at the Sim live edge -- the Scanner stays live.
 * Off the edge it reads `GET /api/leaderboard/{date}?at=` once per board
 * minute (the playhead moving inside a minute asks nothing), and states a gap,
 * a load or a failure instead of a board. The previous board is kept while
 * the next one loads only when it is exactly the minute before on the same
 * day (plain playback); after a jump or across a gap nothing old is shown.
 */
import { useEffect, useState } from 'react';
import { replayRequest } from '../sim/replayRequest';
import { simClockResource } from '../sim/simClockResource';
import {
  LEADERBOARD_PLAYBACK_RETRY_MS,
  LEADERBOARD_REQUEST_FAILED,
  leaderboardBoardPath,
} from './leaderboardConstants';
import { parseLeaderboardAt } from './leaderboardParse';
import { replayFromAnswer, replayPending } from './leaderboardRows';
import type { ScannerReplay } from './leaderboardTypes';
import { playheadSecondIn, useSimPlayheadMinute } from './simPlayhead';

/** Keep `prev` while `minute` loads? Only the board of the minute just before, same day, no gap. */
export function keepWhileLoading(prev: ScannerReplay | null, date: string, minute: number): boolean {
  if (!prev || prev.date !== date) return false;
  if (prev.minute === minute) return true;
  return prev.status === 'ready' && prev.gap == null && prev.minuteTs === minute - 60;
}

export function useLeaderboardPlayback(): ScannerReplay | null {
  const playhead = useSimPlayheadMinute();
  const date = playhead?.date ?? null;
  const minute = playhead?.minute ?? null;
  const [state, setState] = useState<ScannerReplay | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (date == null || minute == null) {
      setState(null);
      return undefined;
    }
    const controller = new AbortController();
    let retry: number | undefined;
    setState(prev => (keepWhileLoading(prev, date, minute) ? prev : replayPending(date, minute)));
    const at = playheadSecondIn(minute, simClockResource.getSnapshot().data);
    replayRequest<unknown>(leaderboardBoardPath(date, at), { signal: controller.signal }, LEADERBOARD_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        let next: ScannerReplay;
        try {
          next = replayFromAnswer(date, minute, parseLeaderboardAt(raw));
        } catch (error) {
          next = replayPending(date, minute, error instanceof Error ? error.message : String(error));
        }
        setState(next);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        console.warn('[Nova] Scanner board at the Sim playhead did not load', message);
        setState(replayPending(date, minute, message));
        retry = window.setTimeout(() => setAttempt(n => n + 1), LEADERBOARD_PLAYBACK_RETRY_MS);
      });
    return () => {
      controller.abort();
      window.clearTimeout(retry);
    };
  }, [date, minute, attempt]);

  if (date == null || minute == null) return null;
  // Until the effect has run for this minute, say it is loading -- never another minute's board.
  if (!state || state.date !== date || !keepWhileLoading(state, date, minute)) return replayPending(date, minute);
  return state;
}
