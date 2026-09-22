/**
 * Records -- every day's Session Records from GET /api/capture/sessions
 * (shared poll resource with the Sim header), newest day first, with a link
 * into Trader per row and, on the Sim venue, Replay in Sim. States are stated,
 * never guessed: loading, unavailable, none yet. The listing is parsed at its
 * boundary, recording symbols come from a fresh status only, and counts Nova
 * does not know read as words, never "-1" (QA 2026-09-22, C13 / C14 / C22 /
 * C64 / V20).
 */
import { useState, useSyncExternalStore } from 'react';
import {
  RECORDS_PAGE_COL_MISSING,
  RECORDS_PAGE_COL_PRINTS,
  RECORDS_PAGE_COL_SEGMENTS,
  RECORDS_PAGE_COL_STATUS,
  RECORDS_PAGE_COL_SYMBOL,
  RECORDS_PAGE_EMPTY,
  RECORDS_PAGE_ERROR_PREFIX,
  RECORDS_PAGE_LOADING,
  RECORDS_PAGE_MISSING_TITLE,
  RECORDS_PAGE_OPEN_TRADER,
  RECORDS_PAGE_RECORDING,
  RECORDS_PAGE_REPLAY,
  RECORDS_PAGE_REPLAY_FAILED,
  RECORDS_PAGE_REPLAY_TITLE,
  RECORDS_PAGE_SUBTITLE,
  RECORDS_PAGE_TITLE,
  RECORDS_PAGE_TODAY,
} from '../constantGroups/nav_rail';
import { JOURNAL_CALENDAR_TIMEZONE } from '../constants';
import { useRecordingSymbols } from '../capture/sessionRecordStore';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { selectCaptureReplay } from '../sim/captureReplayLoad';
import {
  recordingUnavailableReason, recordingUsable, recordPrintsCell, recordStatusWords,
} from '../sim/captureRowFormat';
import { CAPTURE_PRINTS_RECORDING } from '../sim/simConstants';
import { useReplayActions } from '../sim/useReplayActions';
import { capturesResource, type CaptureSessionRow } from '../sim/useSimSessionController';
import '../styles/rail-pages.css';

interface Props {
  onOpenTrader: (symbol: string) => void;
}

/** Calendar day in America/New_York as YYYY-MM-DD (the backend's session_date). */
export function todayEasternDate(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: JOURNAL_CALENDAR_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

/** "42s" / "1m 05s" / "5h 12m" for the seconds no segment covers; "--" for none or unknown. */
export function formatMissingSeconds(sec: number | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '--';
  const total = Math.round(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}

/** Segments on disk; the one still recording counts even before its first stop. */
function segmentsCell(row: CaptureSessionRow, recording: boolean): string {
  if (row.segments != null && row.segments > 0) return String(row.segments);
  return recording ? CAPTURE_PRINTS_RECORDING : '--';
}

function rowStatus(row: CaptureSessionRow, recording: boolean): string {
  if (recording) return RECORDS_PAGE_RECORDING;
  return recordingUnavailableReason(row) ?? recordStatusWords(row) ?? '--';
}

/** "Mon, Sep 21" for a YYYY-MM-DD day heading. */
function dayLabel(date: string): string {
  const day = new Date(`${date}T12:00:00Z`);
  if (!Number.isFinite(day.getTime())) return date;
  return day.toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' });
}

export function RecordsPage({ onOpenTrader }: Props) {
  const { data, error } = useSyncExternalStore(capturesResource.subscribe, capturesResource.getSnapshot);
  const recording = new Set(useRecordingSymbols());
  const sim = useIbkrStatus().mode === 'sim';
  const { request, busy, errors } = useReplayActions();
  const [replayError, setReplayError] = useState<string | null>(null);
  const today = todayEasternDate();
  const byDay = data?.tickers_by_day ?? {};
  // Every day with records, newest first -- today's calendar date is not the
  // only one worth reaching (V20: at 01:30 ET yesterday's session is the live one).
  const days = Object.keys(byDay).filter(date => (byDay[date] ?? []).length > 0).sort().reverse();

  const replay = async (date: string, symbol: string) => {
    setReplayError(null);
    const result = await selectCaptureReplay(request, date, symbol);
    if (!result) return;
    if (result.clock.replay_ok === false) setReplayError(result.clock.replay_error || null);
    else onOpenTrader(symbol);
  };
  const failure = errors.replay ?? replayError;

  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <section className="panel rail-page" aria-label={RECORDS_PAGE_TITLE} data-testid="records-page">
          <h2 className="rail-page__title">{RECORDS_PAGE_TITLE}</h2>
          <p className="rail-page__sub">{RECORDS_PAGE_SUBTITLE}</p>
          {recording.size > 0 && (
            <p className="records-page__recording" data-testid="records-page-recording">
              {RECORDS_PAGE_RECORDING}: {[...recording].join(', ')}
            </p>
          )}
          {failure && (
            <p className="rail-page__note" role="alert" data-testid="records-page-replay-error">
              {RECORDS_PAGE_REPLAY_FAILED} {failure}
            </p>
          )}
          {error && !data ? (
            <p className="rail-page__note" role="alert">
              {RECORDS_PAGE_ERROR_PREFIX} {error}
            </p>
          ) : !data ? (
            <p className="rail-page__note">{RECORDS_PAGE_LOADING}</p>
          ) : days.length === 0 ? (
            <p className="rail-page__note" data-testid="records-page-empty">{RECORDS_PAGE_EMPTY}</p>
          ) : (
            <>
              {error && (
                <p className="rail-page__note" role="alert">
                  {RECORDS_PAGE_ERROR_PREFIX} {error}
                </p>
              )}
              {days.map(date => (
                <div key={date} data-testid={`records-day-${date}`}>
                  <h3 className="rail-page__sub">
                    {dayLabel(date)} · {date}{date === today ? ` · ${RECORDS_PAGE_TODAY}` : ''}
                  </h3>
                  <table className="records-page__table" data-testid="records-page-table">
                    <thead>
                      <tr>
                        <th>{RECORDS_PAGE_COL_SYMBOL}</th>
                        <th>{RECORDS_PAGE_COL_PRINTS}</th>
                        <th>{RECORDS_PAGE_COL_SEGMENTS}</th>
                        <th title={RECORDS_PAGE_MISSING_TITLE}>{RECORDS_PAGE_COL_MISSING}</th>
                        <th>{RECORDS_PAGE_COL_STATUS}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {(byDay[date] ?? []).map((row) => {
                        // Only today's row can be the one recording now.
                        const live = date === today && recording.has(row.symbol);
                        return (
                          <tr key={row.symbol} data-testid={`records-row-${date}-${row.symbol}`}>
                            <td>{row.symbol}</td>
                            <td className="is-num">{recordPrintsCell(row.prints, live)}</td>
                            <td className="is-num">{segmentsCell(row, live)}</td>
                            <td className="is-num">{formatMissingSeconds(row.missing_sec)}</td>
                            <td>{rowStatus(row, live)}</td>
                            <td>
                              {sim && recordingUsable(row) && (
                                <button
                                  type="button"
                                  className="records-page__open"
                                  data-testid={`records-replay-${date}-${row.symbol}`}
                                  title={RECORDS_PAGE_REPLAY_TITLE}
                                  disabled={busy.has('replay')}
                                  onClick={() => void replay(date, row.symbol)}
                                >
                                  {RECORDS_PAGE_REPLAY}
                                </button>
                              )}{' '}
                              <button
                                type="button"
                                className="records-page__open"
                                data-testid={`records-open-${date}-${row.symbol}`}
                                onClick={() => onOpenTrader(row.symbol)}
                              >
                                {RECORDS_PAGE_OPEN_TRADER}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
