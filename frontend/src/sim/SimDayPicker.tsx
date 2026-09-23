/**
 * The Sim Day calendar (ADR 023): every day with something on file, five years
 * back, and what each day has -- a Scanner board recorded by Nova, the
 * operator's own Session Records, a board rebuilt from minute bars -- each
 * marked from its own source. Picking a day posts `/api/sim/clock
 * {session_date}`: Sim moves there with nothing loaded, parked paused at
 * 07:00 ET, and the Scanner board and HOD strip follow the playhead. "Today"
 * posts `{session_date: null}` (the live edge). The ⋯ menu's Day select stays
 * the Session Record picker for replay loads.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  SIM_DAY_CAL_CLOSED,
  SIM_DAY_CAL_NEXT,
  SIM_DAY_CAL_NOTHING,
  SIM_DAY_CAL_PREV,
  SIM_DAY_CAL_REBUILT,
  SIM_DAY_CAL_RECORDED,
  SIM_DAY_CAL_SESSIONS,
  SIM_DAY_CAL_TODAY,
  SIM_DAY_CAL_WEEKDAYS,
  SIM_DAY_CAL_YEAR,
  SIM_DAY_PICKER_LABEL,
  SIM_DAY_PICKER_REBUILT,
  SIM_DAY_PICKER_RECORDED,
  SIM_DAY_PICKER_TITLE,
  SIM_DAY_PICKER_TODAY,
  simDayCalSessions,
} from '../leaderboard/leaderboardConstants';
import type { LeaderboardDay } from '../leaderboard/leaderboardTypes';
import {
  type CalendarDayFacts,
  cellTitle,
  dayFacts,
  monthGrid,
  monthIndex,
  monthOf,
  monthRange,
  shiftMonth,
  type MonthRef,
} from './simDayCalendarModel';
import type { SimClockState } from './simClockTypes';
import { formatShortDate, todayEt } from './simStripFormat';
import type { CaptureSessions } from './useSimSessionController';
import './simDayCalendar.css';

interface Props {
  clock: SimClockState | null;
  days: LeaderboardDay[];
  /** The operator's Session Records (`GET /api/capture/sessions`), to mark the days they recorded. */
  sessions?: CaptureSessions | null;
  /** Why the day list is missing, stated in the picker's title. */
  error?: string | null;
  busy: boolean;
  onOpen: () => void;
  onPick: (date: string | null) => void;
  today?: string;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Sep 21 · rec", "Sep 18 · rebuilt", "Sep 22 · rec + rebuilt". */
export function dayOptionLabel(day: LeaderboardDay): string {
  const kinds = [day.recorded ? SIM_DAY_PICKER_RECORDED : null, day.reconstructed ? SIM_DAY_PICKER_REBUILT : null]
    .filter(Boolean)
    .join(' + ');
  return `${formatShortDate(day.date)} · ${kinds}`;
}

function factsWord(facts: CalendarDayFacts | undefined): string {
  if (!facts) return '';
  const kinds = [
    facts.recorded ? SIM_DAY_PICKER_RECORDED : null,
    facts.rebuilt ? SIM_DAY_PICKER_REBUILT : null,
  ].filter(Boolean).join(' + ');
  return kinds ? ` · ${kinds}` : '';
}

export function SimDayPicker({ clock, days, sessions = null, error = null, busy, onOpen, onPick, today = todayEt() }: Props) {
  const [open, setOpen] = useState(false);
  const facts = useMemo(() => dayFacts(days, sessions), [days, sessions]);
  const range = useMemo(() => monthRange(facts, today), [facts, today]);
  const date = clock?.session_date ?? '';
  // Today at the live edge is "Today"; today scrubbed back is that day like any other.
  const selected = date && !(date === today && clock?.live_edge) ? date : null;
  const [view, setView] = useState<MonthRef>(() => monthOf(selected ?? today));
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const onDown = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  const toggle = () => {
    if (!open) {
      onOpen();
      setView(monthOf(selected ?? today));
    }
    setOpen(!open);
  };
  const pick = (value: string | null) => {
    setOpen(false);
    onPick(value);
  };
  const clamp = (ref: MonthRef) =>
    (monthIndex(ref) < monthIndex(range.first) ? range.first : monthIndex(ref) > monthIndex(range.last) ? range.last : ref);
  const weeks = monthGrid(view, facts, today, selected);
  const years: number[] = [];
  for (let y = range.last.year; y >= range.first.year; y -= 1) years.push(y);
  const labels = {
    rebuilt: SIM_DAY_CAL_REBUILT, recorded: SIM_DAY_CAL_RECORDED, sessions: simDayCalSessions,
    nothing: SIM_DAY_CAL_NOTHING, closed: SIM_DAY_CAL_CLOSED,
  };

  return (
    <div className="sim-strip__day sim-day" ref={root} title={error ? `${SIM_DAY_PICKER_TITLE}\n${error}` : SIM_DAY_PICKER_TITLE}>
      <span>{SIM_DAY_PICKER_LABEL}</span>
      <button
        type="button"
        className="sim-day__button"
        data-testid="sim-strip-day"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={busy || !clock?.sim}
        onClick={toggle}
      >
        {selected ? `${formatShortDate(selected)}${factsWord(facts.get(selected))}` : SIM_DAY_PICKER_TODAY} ▾
      </button>
      {open ? (
        <div className="sim-day__pop" role="dialog" aria-label={SIM_DAY_PICKER_LABEL} data-testid="sim-day-calendar">
          <div className="sim-day__head">
            <button type="button" aria-label={SIM_DAY_CAL_PREV} data-testid="sim-day-prev"
              disabled={monthIndex(view) <= monthIndex(range.first)} onClick={() => setView(clamp(shiftMonth(view, -1)))}>‹</button>
            <span className="sim-day__month" data-testid="sim-day-month">{MONTHS[view.month0]}</span>
            <select aria-label={SIM_DAY_CAL_YEAR} data-testid="sim-day-year" value={view.year}
              onChange={e => setView(clamp({ year: Number(e.target.value), month0: view.month0 }))}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <button type="button" aria-label={SIM_DAY_CAL_NEXT} data-testid="sim-day-next"
              disabled={monthIndex(view) >= monthIndex(range.last)} onClick={() => setView(clamp(shiftMonth(view, 1)))}>›</button>
          </div>
          <div className="sim-day__grid" role="grid">
            {SIM_DAY_CAL_WEEKDAYS.map((w, i) => <span key={`${w}${i}`} className="sim-day__dow">{w}</span>)}
            {weeks.flat().map(cell => (
              <button
                key={cell.date}
                type="button"
                data-testid={`sim-day-cell-${cell.date}`}
                data-recorded={cell.facts.recorded ? '1' : '0'}
                data-sessions={cell.facts.sessions.length}
                data-rebuilt={cell.facts.rebuilt ? '1' : '0'}
                className={[
                  'sim-day__cell',
                  cell.inMonth ? '' : 'is-other',
                  cell.weekend ? 'is-weekend' : '',
                  cell.facts.recorded ? 'is-recorded' : '',
                  cell.facts.rebuilt ? 'is-rebuilt' : '',
                  cell.selected ? 'is-selected' : '',
                  cell.today ? 'is-today' : '',
                ].filter(Boolean).join(' ')}
                disabled={!cell.selectable}
                title={cellTitle(cell, labels)}
                onClick={() => pick(cell.date)}
              >
                {cell.day}
                {cell.facts.sessions.length ? <i className="sim-day__rec" aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
          <div className="sim-day__legend">
            <span><i className="sim-day__swatch is-recorded" />{SIM_DAY_CAL_RECORDED}</span>
            <span><i className="sim-day__rec sim-day__rec--legend" />{SIM_DAY_CAL_SESSIONS}</span>
            <span><i className="sim-day__swatch is-rebuilt" />{SIM_DAY_CAL_REBUILT}</span>
          </div>
          <button type="button" className="sim-day__today" data-testid="sim-day-today" onClick={() => pick(null)}>
            {SIM_DAY_CAL_TODAY}
          </button>
        </div>
      ) : null}
    </div>
  );
}
