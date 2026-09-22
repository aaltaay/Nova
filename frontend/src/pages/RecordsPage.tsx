/**
 * Records placeholder -- today's Session Records from GET /api/capture/sessions
 * (shared poll resource with the Sim header), with a link into Trader per row.
 * States are stated, never guessed: loading, unavailable, none today.
 */
import { useSyncExternalStore } from 'react';
import {
  RECORDS_PAGE_COL_MISSING,
  RECORDS_PAGE_COL_PRINTS,
  RECORDS_PAGE_COL_SEGMENTS,
  RECORDS_PAGE_COL_STATUS,
  RECORDS_PAGE_COL_SYMBOL,
  RECORDS_PAGE_EMPTY,
  RECORDS_PAGE_ERROR_PREFIX,
  RECORDS_PAGE_LOADING,
  RECORDS_PAGE_OPEN_TRADER,
  RECORDS_PAGE_RECORDING,
  RECORDS_PAGE_SUBTITLE,
  RECORDS_PAGE_TITLE,
} from '../constantGroups/nav_rail';
import { JOURNAL_CALENDAR_TIMEZONE } from '../constants';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { capturesResource, type CaptureSessions } from '../sim/useSimSessionController';
import '../styles/rail-pages.css';

interface Props {
  onOpenTrader: (symbol: string) => void;
}

type Row = CaptureSessions['tickers_by_day'][string][number];

/** Calendar day in America/New_York as YYYY-MM-DD (the backend's session_date). */
export function todayEasternDate(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: JOURNAL_CALENDAR_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

export function formatMissingSeconds(sec: number | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '--';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}

function rowStatus(row: Row, recording: boolean): string {
  if (recording) return RECORDS_PAGE_RECORDING;
  if (row.unavailable_reason) return row.unavailable_reason;
  if (row.empty) return 'empty';
  if (row.usable === false) return 'unusable';
  return row.status ?? row.last_reason ?? '--';
}

export function RecordsPage({ onOpenTrader }: Props) {
  const { data, error } = useSyncExternalStore(capturesResource.subscribe, capturesResource.getSnapshot);
  const status = useIbkrStatus();
  const recording = new Set(
    status.capture === true && status.recording === true ? (status.capture_symbols ?? []) : [],
  );
  const today = todayEasternDate();
  const rows: Row[] = data?.tickers_by_day[today] ?? [];

  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <section className="panel rail-page" aria-label={RECORDS_PAGE_TITLE} data-testid="records-page">
          <h2 className="rail-page__title">{RECORDS_PAGE_TITLE}</h2>
          <p className="rail-page__sub">
            {RECORDS_PAGE_SUBTITLE} · {today}
          </p>
          {recording.size > 0 && (
            <p className="records-page__recording" data-testid="records-page-recording">
              {RECORDS_PAGE_RECORDING}: {[...recording].join(', ')}
            </p>
          )}
          {error ? (
            <p className="rail-page__note" role="alert">
              {RECORDS_PAGE_ERROR_PREFIX} {error}
            </p>
          ) : !data ? (
            <p className="rail-page__note">{RECORDS_PAGE_LOADING}</p>
          ) : rows.length === 0 ? (
            <p className="rail-page__note" data-testid="records-page-empty">{RECORDS_PAGE_EMPTY}</p>
          ) : (
            <table className="records-page__table" data-testid="records-page-table">
              <thead>
                <tr>
                  <th>{RECORDS_PAGE_COL_SYMBOL}</th>
                  <th>{RECORDS_PAGE_COL_PRINTS}</th>
                  <th>{RECORDS_PAGE_COL_SEGMENTS}</th>
                  <th>{RECORDS_PAGE_COL_MISSING}</th>
                  <th>{RECORDS_PAGE_COL_STATUS}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol} data-testid={`records-row-${row.symbol}`}>
                    <td>{row.symbol}</td>
                    <td className="is-num">{row.prints.toLocaleString()}</td>
                    <td className="is-num">{row.segments ?? '--'}</td>
                    <td className="is-num">{formatMissingSeconds(row.missing_sec)}</td>
                    <td>{rowStatus(row, recording.has(row.symbol))}</td>
                    <td>
                      <button
                        type="button"
                        className="records-page__open"
                        data-testid={`records-open-${row.symbol}`}
                        onClick={() => onOpenTrader(row.symbol)}
                      >
                        {RECORDS_PAGE_OPEN_TRADER}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
