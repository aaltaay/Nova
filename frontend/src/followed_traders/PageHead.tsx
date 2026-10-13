/**
 * The page's head: title, the capture pill, the day (previous / calendar / next among the feed's days) and the
 * Alerts switch. Previous and next step through days the feed has; one with nowhere to go is disabled and says why.
 */
import { useEffect, useRef, useState } from 'react';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import { dayLabel, neighbourDay } from './calendar';
import { capturePill } from './capture';
import {
  FT_ALERTS_OFF,
  FT_ALERTS_ON,
  FT_ALERTS_TIP,
  FT_NEXT_DAY,
  FT_NO_NEXT_DAY,
  FT_NO_PREV_DAY,
  FT_PREV_DAY,
  FT_SUBTITLE,
  FT_TITLE,
  FT_TODAY,
} from './constants';
import { DayPicker } from './DayPicker';
import { setFollowedAlerts, useFollowedAlerts } from './followedStores';
import type { FollowedDay } from './types';

interface Props {
  day: FollowedDay;
  onPickDate: (date: string | null) => void;
}

export function PageHead({ day, onPickDate }: Props) {
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
      <div className="ft-head__titles">
        <h1 className="ft-head__title">{FT_TITLE}</h1>
        <span className="ft-muted">{FT_SUBTITLE}</span>
        {day.capture?.title && <span className="ft-muted ft-small ft-ellipsis" title={day.capture.title}>{day.capture.title}</span>}
      </div>
      <div className="ft-head__tools">
        {pill && (
          <span className={`ft-status ft-status--${pill.tone}`} data-testid="ft-capture-pill" role="status">
            <span className="ft-status__dot" aria-hidden="true" />
            {pill.text}
          </span>
        )}
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
