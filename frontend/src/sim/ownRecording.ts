/**
 * A Sim tab with nothing loaded should offer the operator's own Session Record
 * of that symbol before a historical download: it carries the recorded book
 * and tape, and it is selectable while still recording.
 */
import type { CaptureSessions } from './useSimSessionController';

export interface OwnRecording {
  date: string;
  symbol: string;
  prints: number;
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
    const row = (sessions.tickers_by_day?.[date] ?? []).find(
      (t) => t.symbol.toUpperCase() === sym && t.usable !== false && !t.empty,
    );
    if (row) return { date, symbol: sym, prints: row.prints, recording: date === today && (row.status === 'recording') };
  }
  return null;
}
