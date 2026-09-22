/**
 * A Sim tab with nothing loaded should offer the operator's own Session Record
 * of that symbol before a historical download: it carries the recorded book
 * and tape, and it is selectable while still recording.
 */
import { recordingUsable } from './captureRowFormat';
import type { CaptureSessions } from './useSimSessionController';

export interface OwnRecording {
  date: string;
  symbol: string;
  /** Recorded prints; null while Nova has not counted them (a first segment still recording). */
  prints: number | null;
  recording: boolean;
}

/** Today's date in America/New_York as YYYY-MM-DD. */
export function etDateToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

/** The newest usable recording of `symbol`, today's first; null when there is none. */
export function ownRecordingFor(
  sessions: CaptureSessions | null | undefined,
  symbol: string,
  today: string = etDateToday(),
): OwnRecording | null {
  if (!sessions) return null;
  const sym = symbol.trim().toUpperCase();
  const dates = Object.keys(sessions.tickers_by_day ?? {}).sort().reverse();
  for (const date of [today, ...dates.filter((d) => d !== today)]) {
    const rows = sessions.tickers_by_day?.[date];
    const row = (Array.isArray(rows) ? rows : []).find(
      (t) => String(t.symbol ?? '').toUpperCase() === sym && recordingUsable(t),
    );
    if (row) return { date, symbol: sym, prints: row.prints ?? null, recording: date === today && row.status === 'recording' };
  }
  return null;
}
