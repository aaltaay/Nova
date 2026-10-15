/**
 * The page's head, one row: title, the capture pill, the stream's title and Watch live, the record span with
 * everyone's record, why open positions are not priced (when they are not), the day (previous / calendar / next
 * among the feed's days), when today resets (04:00 ET, the desk's own day) and the Alerts switch. Previous and next
 * step through days the feed has; one with nowhere to go is disabled and says why, as is Watch live when the feed
 * names no stream or the stream is not live.
 */
import { useEffect, useRef, useState } from 'react';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import { dayLabel, neighbourDay } from './calendar';
import { capturePill } from './capture';
import { etDay, etHour } from './format';
import {
  FT_EVERYONE,
  FT_LAST_STREAM,
  FT_NO_STREAM,
  FT_RECORD_PENDING,
  FT_RECORD_RANGES,
  FT_RECORDS,
  FT_RESETS,
  FT_STREAM_OFFLINE,
  FT_STREAM_SHOWING,
  FT_WATCH_LIVE,
  FT_ALERTS_OFF,
  FT_ALERTS_ON,
  FT_ALERTS_TIP,
  FT_NEXT_DAY,
  FT_NO_NEXT_DAY,
  FT_NO_PREV_DAY,
  FT_PREV_DAY,
  FT_TITLE,
  FT_TODAY,
} from './constants';
import { DayPicker } from './DayPicker';
import { setFollowedAlerts, useFollowedAlerts } from './followedStores';
import { RecordChips } from './parts';
import { setStreamOpen } from './stream';
import type { FollowedDay, FollowedRecord, RecordRange } from './types';

export interface RecordsHead {
  range: RecordRange;
  onRange: (r: RecordRange) => void;
  overall: FollowedRecord | null;
  error: string | null;
  pending: number;
}

interface Props {
  day: FollowedDay;
  onPickDate: (date: string | null) => void;
  /** Absent while the feed is down: there is no record to show. */
  records: RecordsHead | null;
  /** Why open positions are not priced now, or null. */
  pricesWhy: string | null;
  /** The stream the feed names, whether its player is open in this window, whether it is live, and why not. */
  stream: { id: string | null; open: boolean; live: boolean; offAirWhy: string | null };
}

/** When today ends and what happens then, in words for the hover. */
function resetTip(resetsAt: number): string {
  return `Today runs until ${etHour(resetsAt)} ET on ${etDay(resetsAt)}, the premarket, when the rest of the desk `
    + 'starts its day too. Then the page starts the new day empty: records, Holding now and Closed today begin '
    + 'again, and a position still on a trader’s bar shows as already open once the feed reads the stream.';
}

function Records({ r }: { r: RecordsHead }) {
  return (
    <div className="ft-records" data-testid="ft-records">
      <div className="ft-segmented" role="group" aria-label={FT_RECORDS}>
        {(Object.keys(FT_RECORD_RANGES) as RecordRange[]).map((k) => (
          <button key={k} type="button" aria-pressed={r.range === k} className={r.range === k ? 'is-on' : undefined}
            onClick={() => r.onRange(k)} data-testid={`ft-range-${k}`}>{FT_RECORD_RANGES[k]}</button>
        ))}
      </div>
      <span className="ft-records__everyone">
        <span className="ft-muted ft-small">{FT_EVERYONE}</span>
        <RecordChips record={r.overall} testId="ft-record-everyone" />
      </span>
      {r.range !== 'day' && r.error && <span className="ft-small ft-warn-text">{r.error}</span>}
      {r.range !== 'day' && r.pending > 0 && <span className="ft-xs ft-muted">{r.pending} {FT_RECORD_PENDING}</span>}
    </div>
  );
}

export function PageHead({ day, onPickDate, records, pricesWhy, stream }: Props) {
  const [open, setOpen] = useState(false);
  const alertsOn = useFollowedAlerts();
  const wrap = useRef<HTMLDivElement>(null);
  const pill = capturePill(day);
  const today = day.today;
  const shown = day.date ?? today;
  const isToday = shown !== null && shown === today;
  const prev = shown ? neighbourDay(day.dates, shown, -1) : null;
  // After the newest past day comes today, whether or not the feed has trades on it yet.
  const next = shown && !isToday ? neighbourDay(day.dates.filter((d) => !today || d < today), shown, 1) ?? today : null;
  const resetsAt = isToday ? day.resets_at ?? null : null;
  const watchWhy = !stream.id ? FT_NO_STREAM : !stream.live ? `${FT_STREAM_OFFLINE} · ${stream.offAirWhy ?? ''}` : null;
  const watching = !watchWhy && stream.open;

  useEffect(() => {
    if (!open) return undefined;
    const away = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const go = (date: string | null) => {
    setOpen(false);
    onPickDate(date === today ? null : date);
  };

  return (
    <div className="ft-head">
      <h1 className="ft-head__title">{FT_TITLE}</h1>
      {pill && (
        <span className={`ft-status ft-status--${pill.tone}`} data-testid="ft-capture-pill" role="status" title={pill.title}>
          <span className="ft-status__dot" aria-hidden="true" />
          <span className="ft-ellipsis">{pill.text}</span>
        </span>
      )}
      {day.capture?.title && (
        <span className="ft-muted ft-small ft-ellipsis ft-head__video" title={day.capture.title} data-testid="ft-head-video">
          {stream.live ? day.capture.title : `${FT_LAST_STREAM} ${day.capture.title}`}
        </span>
      )}
      <button type="button" className={`ft-btn ft-watch${watching ? ' is-on' : ''}`} disabled={!!watchWhy}
        aria-pressed={watching} {...whyProps(!!watchWhy, watchWhy)}
        {...tipProps(watching ? FT_STREAM_SHOWING : null)} onClick={() => setStreamOpen(true)}
        data-testid="ft-watch-live">▶ {FT_WATCH_LIVE}</button>
      <span className="ft-head__spacer" />
      {records && <Records r={records} />}
      {pricesWhy && <span className="ft-status ft-status--warn ft-small" data-testid="ft-prices">Prices now: {pricesWhy}</span>}
      <div className="ft-head__tools">
        <div className="ft-daynav" ref={wrap} onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}>
          <button type="button" className="ft-btn" aria-label={FT_PREV_DAY} disabled={!prev}
            {...whyProps(!prev, FT_NO_PREV_DAY)} {...tipProps(prev ? `${FT_PREV_DAY}: ${dayLabel(prev)}` : null)}
            onClick={() => prev && go(prev)} data-testid="ft-prev-day">‹</button>
          <button type="button" className="ft-btn ft-btn--day" aria-expanded={open} aria-haspopup="dialog"
            onClick={() => setOpen((o) => !o)} data-testid="ft-day-button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" />
              <path d="M3 10h18M8 3v4M16 3v4" /></svg>
            {shown ? (isToday ? `${FT_TODAY} · ${dayLabel(shown)}` : dayLabel(shown)) : FT_TODAY}
          </button>
          <button type="button" className="ft-btn" aria-label={FT_NEXT_DAY} disabled={!next}
            {...whyProps(!next, FT_NO_NEXT_DAY)} {...tipProps(next ? `${FT_NEXT_DAY}: ${dayLabel(next)}` : null)}
            onClick={() => next && go(next)} data-testid="ft-next-day">›</button>
          {open && today && shown && <DayPicker today={today} shown={shown} dates={day.dates} onOpen={go} />}
        </div>
        {resetsAt !== null && (
          <span className="ft-xs ft-muted ft-nowrap" {...tipProps(resetTip(resetsAt))} data-testid="ft-day-reset">
            {FT_RESETS} {etHour(resetsAt)} ET
          </span>
        )}
        <button type="button" className={`ft-btn ft-alerts${alertsOn ? ' is-on' : ''}`} aria-pressed={alertsOn}
          {...tipProps(FT_ALERTS_TIP)} onClick={() => setFollowedAlerts(!alertsOn)} data-testid="ft-alerts">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" aria-hidden="true"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
            <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></svg>
          {alertsOn ? FT_ALERTS_ON : FT_ALERTS_OFF}
        </button>
      </div>
    </div>
  );
}
