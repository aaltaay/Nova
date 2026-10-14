/**
 * A rebuilt day's Gappers by the second (ADR 023 amendment 2026-10-13): on a rebuilt day with a Gappers list the
 * desk asks for the day's build once (`POST /api/leaderboard/{date}/seconds`), then reads the list at each
 * playhead second (`GET ...?at=`), and again every `LEADERBOARD_SECONDS_POLL_MS` while the build is asked for or
 * runs, or a read failed. A day the backend says cannot be built keeps that answer and is not read again.
 * Recorded days, Live and Paper ask nothing. `withGappersBySecond` decides what the Scanner shows.
 */
import { useEffect, useState } from 'react';
import { replayRequest } from '../sim';
import { type GappersBySecondAnswer, gappersBySecondDay } from './gappersBySecond';
import {
  LEADERBOARD_SECONDS_POLL_MS,
  LEADERBOARD_SECONDS_REQUEST_FAILED,
  leaderboardSecondsAtPath,
  leaderboardSecondsPath,
} from './leaderboardConstants';
import { parseLeaderboardSecondsAt } from './leaderboardParse';
import type { ScannerReplay } from './leaderboardTypes';
import { useSimPlayheadSecond } from './simPlayhead';

const message = (error: unknown): string => (error instanceof Error ? error.message : String(error));

export interface GappersBySecondFeed {
  latest: GappersBySecondAnswer | null;
  second: number | null;
}

export function useGappersBySecond(replay: ScannerReplay | null): GappersBySecondFeed {
  const date = gappersBySecondDay(replay);
  const second = useSimPlayheadSecond(date != null);
  const [asked, setAsked] = useState<GappersBySecondAnswer | null>(null);
  const [read, setRead] = useState<GappersBySecondAnswer | null>(null);
  const [poll, setPoll] = useState(0);

  // Ask for the day's build once; a day that cannot be built keeps the backend's reason.
  useEffect(() => {
    if (date == null) return undefined;
    const controller = new AbortController();
    replayRequest<unknown>(leaderboardSecondsPath(date), { method: 'POST', signal: controller.signal },
      LEADERBOARD_SECONDS_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        setAsked({ date, asked: null, answer: parseLeaderboardSecondsAt(raw), error: null });
        setPoll(n => n + 1);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAsked({ date, asked: null, answer: null, error: message(error) });
      });
    return () => controller.abort();
  }, [date]);

  const refused = asked?.date === date && (asked?.error != null || asked?.answer?.status === 'unavailable');

  useEffect(() => {
    if (date == null || second == null || refused) return undefined;
    const controller = new AbortController();
    replayRequest<unknown>(leaderboardSecondsAtPath(date, second), { signal: controller.signal },
      LEADERBOARD_SECONDS_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        setRead({ date, asked: second, answer: parseLeaderboardSecondsAt(raw), error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        console.warn('[Nova] Gappers by the second did not load', message(error));
        setRead(prev => ({ date, asked: second, answer: prev?.date === date ? prev.answer : null, error: message(error) }));
      });
    return () => controller.abort();
  }, [date, second, poll, refused]);

  const latest = date == null ? null
    : refused ? asked
      : read?.date === date ? read
        : asked?.date === date ? asked : null;
  const status = latest?.answer?.status;
  const waiting = latest != null && !refused && (latest.error != null || status === 'queued' || status === 'building');
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = window.setInterval(() => setPoll(n => n + 1), LEADERBOARD_SECONDS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting]);

  return { latest, second };
}
