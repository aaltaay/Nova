/**
 * A rebuilt day's Gappers by the second (ADR 023 amendment 2026-10-13): on a rebuilt day with a Gappers list the
 * desk asks for the day's build once (`POST /api/leaderboard/{date}/seconds`), then reads the list at each
 * playhead second (`GET ...?at=`), and again every `LEADERBOARD_SECONDS_POLL_MS` while the build is asked for or
 * runs, or a read failed. Only the backend's own `unavailable` answer is final: a request that failed (a backend
 * restarting, a dropped connection) is asked again every `LEADERBOARD_SECONDS_POLL_MS`, and nothing is read until
 * one lands -- the ask is what rebuilds a day whose board changed, so a read before it could show the old build.
 * A read answering `none` after an accepted ask (the build is of a rebuilt day since replaced) asks again, and a
 * ready list is read again every `LEADERBOARD_SECONDS_RECHECK_MS` even with the playhead paused.
 * Recorded days, Live and Paper ask nothing. `withGappersBySecond` decides what the Scanner shows.
 */
import { useEffect, useState } from 'react';
import { replayRequest } from '../sim';
import { type GappersBySecondAnswer, gappersBySecondDay } from './gappersBySecond';
import {
  LEADERBOARD_SECONDS_POLL_MS,
  LEADERBOARD_SECONDS_RECHECK_MS,
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
  const [askAgain, setAskAgain] = useState(0);

  // Ask for the day's build; a request that failed is asked again, a day that cannot be built keeps its reason.
  useEffect(() => {
    if (date == null) return undefined;
    const controller = new AbortController();
    let retry: number | undefined;
    replayRequest<unknown>(leaderboardSecondsPath(date), { method: 'POST', signal: controller.signal },
      LEADERBOARD_SECONDS_REQUEST_FAILED)
      .then((raw) => {
        if (controller.signal.aborted) return;
        setAsked({ date, asked: null, answer: parseLeaderboardSecondsAt(raw), error: null });
        setRead(null);                              // a read from before this ask may be of an older build
        setPoll(n => n + 1);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAsked({ date, asked: null, answer: null, error: message(error) });
        retry = window.setTimeout(() => setAskAgain(n => n + 1), LEADERBOARD_SECONDS_POLL_MS);
      });
    return () => {
      controller.abort();
      window.clearTimeout(retry);
    };
  }, [date, askAgain]);

  // Reads start once an ask for this day has landed (it is what rebuilds a day whose board changed), never
  // while it is in flight or failing, and never for a day the backend refused.
  const ours = asked?.date === date ? asked : null;
  const refused = ours != null && (ours.error != null || ours.answer?.status === 'unavailable');
  const readable = ours?.answer != null && !refused;

  useEffect(() => {
    if (date == null || second == null || !readable) return undefined;
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
  }, [date, second, poll, readable]);

  const latest = date == null ? null
    : readable && read?.date === date ? read
      : ours;
  const status = latest?.answer?.status;
  const waiting = latest != null && !refused && (latest.error != null || status === 'queued' || status === 'building');
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = window.setInterval(() => setPoll(n => n + 1), LEADERBOARD_SECONDS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting]);

  // A read that answers `none` after the ask was accepted is a build of a rebuilt day since replaced: ask again,
  // which builds it again. A ready list is read again now and then even with the playhead paused, so that answer
  // can come.
  const replaced = readable && read?.date === date && read.error == null && status === 'none';
  useEffect(() => {
    if (!replaced) return undefined;
    const timer = window.setTimeout(() => setAskAgain(n => n + 1), LEADERBOARD_SECONDS_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [replaced]);
  const ready = readable && status === 'ready';
  useEffect(() => {
    if (!ready) return undefined;
    const timer = window.setInterval(() => setPoll(n => n + 1), LEADERBOARD_SECONDS_RECHECK_MS);
    return () => window.clearInterval(timer);
  }, [ready]);

  return { latest, second };
}
