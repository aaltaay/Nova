/**
 * What the desk says about a Session Record -- pure, from /api/ibkr/status.
 *
 * Steady state is quiet (chip, hairline, window title); an unrequested stop is
 * loud (a toast that stays until it is resumed or dismissed). Both read the
 * same status snapshot the tab strip reads, so a recording never looks alive
 * in one place and dead in another.
 */
import type { IbkrStatus, RecordingStopped } from '../ibkr/types';

export interface RecordingView {
  symbol: string;
  /** Milliseconds since the session's first segment began; null if unknown. */
  sinceMs: number | null;
  /** Milliseconds this segment has been running -- what "recording for" means after a resume. */
  segmentSinceMs: number | null;
  segment: number | null;
  prints: number;
  quotes: number;
  l2: number;
  lastWriteAgeSec: number | null;
  reacquired: number;
  dir: string | null;
}

export interface ResumeView {
  pending: boolean;
  attempt: number;
  maxAttempts: number;
  /** Seconds until the next automatic attempt; 0 when due. */
  nextInSec: number;
  gaveUp: boolean;
  gaveUpReason: string | null;
}

export interface StoppedView {
  /** One toast per stop: symbol + when. */
  key: string;
  symbol: string;
  reason: string;
  error: string | null;
  atMs: number;
  prints: number;
  resume: ResumeView | null;
}

function count(counts: Record<string, number> | undefined, key: string): number {
  const value = counts?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/** The running recording, or null. `symbol` is the fresh, server-owned one. */
export function recordingView(status: IbkrStatus, symbol: string | null, nowMs: number): RecordingView | null {
  const session = status.capture_session;
  if (!symbol || !session || session.symbol !== symbol) return null;
  const started = session.started_et ? Date.parse(session.started_et) : NaN;
  const segmentStarted = session.segment_started_et ? Date.parse(session.segment_started_et) : NaN;
  const lastWrite = session.last_write_ts;
  return {
    symbol,
    sinceMs: Number.isFinite(started) ? Math.max(0, nowMs - started) : null,
    segmentSinceMs: Number.isFinite(segmentStarted) ? Math.max(0, nowMs - segmentStarted) : null,
    segment: typeof session.segment === 'number' ? session.segment : null,
    prints: count(session.counts, 'prints'),
    quotes: count(session.counts, 'quotes'),
    l2: count(session.counts, 'l2'),
    lastWriteAgeSec: typeof lastWrite === 'number' ? Math.max(0, Math.round(nowMs / 1000 - lastWrite)) : null,
    reacquired: typeof session.reacquired === 'number' ? session.reacquired : 0,
    dir: session.dir ?? null,
  };
}

export function stoppedKey(stopped: RecordingStopped): string {
  return `${stopped.symbol}|${stopped.at}`;
}

/** The stop to shout about, or null once it resumed (the shout is over). */
export function stoppedView(status: IbkrStatus, nowMs: number): StoppedView | null {
  const stopped = status.capture_stopped;
  if (!stopped || stopped.resumed) return null;
  const resume = status.capture_resume;
  return {
    key: stoppedKey(stopped),
    symbol: stopped.symbol,
    reason: stopped.reason,
    error: stopped.error ?? null,
    atMs: stopped.at * 1000,
    prints: count(stopped.counts, 'prints'),
    resume: resume && resume.symbol === stopped.symbol
      ? {
          pending: Boolean(resume.pending) && !resume.gave_up,
          attempt: resume.attempt,
          maxAttempts: resume.max_attempts,
          nextInSec: Math.max(0, Math.ceil(resume.next_at - nowMs / 1000)),
          gaveUp: Boolean(resume.gave_up),
          gaveUpReason: resume.gave_up_reason ?? null,
        }
      : null,
  };
}

/** "12s", "4m 05s", "1h 12m" -- how long a recording has run. */
export function elapsedLabel(ms: number | null): string {
  if (ms == null) return '--';
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}
