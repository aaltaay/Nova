/**
 * `GET /api/leaderboard/days` for the Sim strip's Day picker: every day with
 * a Scanner board, recorded and / or rebuilt, newest first. Read when the
 * picker mounts and again whenever it is opened -- never polled.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { replayRequest } from '../sim/replayRequest';
import { LEADERBOARD_DAYS_PATH, LEADERBOARD_DAYS_REQUEST_FAILED } from './leaderboardConstants';
import { parseLeaderboardDays } from './leaderboardParse';
import type { LeaderboardDay } from './leaderboardTypes';

export interface LeaderboardDaysState {
  days: LeaderboardDay[];
  /** The request failed, or the store said it cannot be read. */
  error: string | null;
  refresh: () => void;
}

const NO_DAYS: LeaderboardDay[] = [];

export function useLeaderboardDays(active: boolean): LeaderboardDaysState {
  const [days, setDays] = useState<LeaderboardDay[]>(NO_DAYS);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef<AbortController | null>(null);

  const refresh = useCallback(() => {
    if (inflight.current) return;
    const controller = new AbortController();
    inflight.current = controller;
    replayRequest<unknown>(LEADERBOARD_DAYS_PATH, { signal: controller.signal }, LEADERBOARD_DAYS_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        const parsed = parseLeaderboardDays(raw);
        setDays(parsed.days);
        setError(parsed.store.ok ? null : parsed.store.error ?? LEADERBOARD_DAYS_REQUEST_FAILED);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (inflight.current === controller) inflight.current = null;
      });
  }, []);

  useEffect(() => {
    if (active) refresh();
    return () => {
      inflight.current?.abort();
      inflight.current = null;
    };
  }, [active, refresh]);

  return { days, error, refresh };
}
