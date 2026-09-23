/**
 * `GET /api/leaderboard/{date}/coverage` for the Sim strip's leaderboard lane:
 * where the Scanner board was recorded (or rebuilt) on the desk's day, and the
 * gaps with their reasons. Read once per day; today's grows while the recorder
 * runs, so it is re-read every LEADERBOARD_COVERAGE_TODAY_REFRESH_MS.
 */
import { useEffect, useState } from 'react';
import { replayRequest } from '../sim/replayRequest';
import {
  LEADERBOARD_COVERAGE_REQUEST_FAILED,
  LEADERBOARD_COVERAGE_TODAY_REFRESH_MS,
  leaderboardCoveragePath,
} from './leaderboardConstants';
import { parseLeaderboardCoverage } from './leaderboardParse';
import type { LeaderboardCoverage } from './leaderboardTypes';

export function useLeaderboardCoverage(date: string | null, today: string): LeaderboardCoverage | null {
  const [coverage, setCoverage] = useState<LeaderboardCoverage | null>(null);

  useEffect(() => {
    setCoverage(null);
    if (!date) return undefined;
    const controller = new AbortController();
    let timer: number | undefined;
    const read = () => {
      replayRequest<unknown>(leaderboardCoveragePath(date), { signal: controller.signal }, LEADERBOARD_COVERAGE_REQUEST_FAILED)
        .then((raw) => {
          if (!controller.signal.aborted) setCoverage({ ...parseLeaderboardCoverage(raw), date });
        })
        .catch((err: unknown) => {
          // No lane is drawn without an answer: an unknown is never drawn as "not recorded".
          if (!controller.signal.aborted) console.warn('[Nova] Scanner board coverage did not load', err);
        })
        .finally(() => {
          if (!controller.signal.aborted && date === today) {
            timer = window.setTimeout(read, LEADERBOARD_COVERAGE_TODAY_REFRESH_MS);
          }
        });
    };
    read();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [date, today]);

  return coverage && coverage.date === date ? coverage : null;
}
