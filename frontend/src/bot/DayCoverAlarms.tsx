/**
 * The day cover's alarm (ADR 048 decision 5, #778 step 6): a short whose cover could not go out -- the venue
 * refused it, IBKR is not connected, or Live stands outside the regular session -- is a red bar across the top
 * of every desk window until a cover goes out or the short is gone. The bot session carries the alarms
 * (`shorts.day_cover`), which every window already polls; this window may hide one for ten minutes at most.
 * Nothing here places an order.
 */
import { useEffect, useState } from 'react';
import {
  DAY_COVER_ALARM_HIDE,
  DAY_COVER_ALARM_HIDE_MS,
  DAY_COVER_ALARM_TITLE,
  DAY_COVER_ALARM_VENUES,
} from '../constantGroups/bots_page';
import { DESK_BOT_POLL_MS } from '../constants';
import { prose } from './botsPageFormat';
import type { CoverAlarm } from './types';
import { useBotSession } from './useBotSession';
import './dayCoverAlarms.css';

/** The alarms this window shows now: every one, less those hidden here until a moment still ahead. */
export function shownAlarms(alarms: readonly CoverAlarm[], hidden: Readonly<Record<string, number>>, now: number): CoverAlarm[] {
  return alarms.filter(a => !(hidden[a.id] > now));
}

export function DayCoverAlarms() {
  const { session } = useBotSession(DESK_BOT_POLL_MS);
  const [hidden, setHidden] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  const alarms = session?.shorts?.day_cover?.alarms ?? [];
  useEffect(() => {
    if (Object.keys(hidden).length === 0) return undefined;
    const t = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(t);
  }, [hidden]);
  const shown = shownAlarms(alarms, hidden, now);
  if (shown.length === 0) return null;
  return (
    <div className="day-cover-alarms" role="alert" aria-live="assertive" data-testid="day-cover-alarms">
      {shown.map(a => (
        <div key={a.id} className="day-cover-alarm" data-testid="day-cover-alarm" data-venue={a.venue}
          data-kind={a.kind}>
          <strong className="day-cover-alarm__title">
            {DAY_COVER_ALARM_TITLE} · {DAY_COVER_ALARM_VENUES[a.venue] ?? a.venue} · {a.symbol} {a.qty} ▼ SHORT
          </strong>
          <span className="day-cover-alarm__text">{prose(a.text)}</span>
          <button type="button" className="day-cover-alarm__hide" data-testid="day-cover-alarm-hide"
            onClick={() => { setHidden(h => ({ ...h, [a.id]: Date.now() + DAY_COVER_ALARM_HIDE_MS })); setNow(Date.now()); }}>
            {DAY_COVER_ALARM_HIDE}
          </button>
        </div>
      ))}
    </div>
  );
}
