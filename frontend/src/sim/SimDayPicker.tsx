/**
 * The Sim strip's Day picker (ADR 022): every day with a Scanner board --
 * recorded by Nova, rebuilt from minute bars, or both -- plus Today. Picking a
 * day posts `/api/sim/clock {session_date}`: Sim moves there with nothing
 * loaded, parked paused at 07:00 ET, and the Scanner board and HOD strip
 * follow the playhead. Today posts `{session_date: null}`. The ⋯ menu's Day
 * select stays what it was: the Session Record picker for replay loads.
 */
import {
  SIM_DAY_PICKER_LABEL,
  SIM_DAY_PICKER_REBUILT,
  SIM_DAY_PICKER_RECORDED,
  SIM_DAY_PICKER_TITLE,
  SIM_DAY_PICKER_TODAY,
} from '../leaderboard/leaderboardConstants';
import type { LeaderboardDay } from '../leaderboard/leaderboardTypes';
import type { SimClockState } from './simClockTypes';
import { formatShortDate, todayEt } from './simStripFormat';

interface Props {
  clock: SimClockState | null;
  days: LeaderboardDay[];
  /** Why the day list is missing, stated in the picker's title. */
  error?: string | null;
  busy: boolean;
  onOpen: () => void;
  onPick: (date: string | null) => void;
  today?: string;
}

/** "Sep 21 · rec", "Sep 18 · rebuilt", "Sep 22 · rec + rebuilt". */
export function dayOptionLabel(day: LeaderboardDay): string {
  const kinds = [day.recorded ? SIM_DAY_PICKER_RECORDED : null, day.reconstructed ? SIM_DAY_PICKER_REBUILT : null]
    .filter(Boolean)
    .join(' + ');
  return `${formatShortDate(day.date)} · ${kinds}`;
}

export function SimDayPicker({ clock, days, error = null, busy, onOpen, onPick, today = todayEt() }: Props) {
  const date = clock?.session_date ?? '';
  const value = date && date !== today ? date : '';
  const listed = days.some(day => day.date === value);
  const pastDays = days.filter(day => day.date !== today);
  return (
    <label className="sim-strip__day" title={error ? `${SIM_DAY_PICKER_TITLE}\n${error}` : SIM_DAY_PICKER_TITLE}>
      <span>{SIM_DAY_PICKER_LABEL}</span>
      <select
        data-testid="sim-strip-day"
        aria-label={SIM_DAY_PICKER_LABEL}
        value={value}
        disabled={busy || !clock?.sim}
        onFocus={onOpen}
        onPointerDown={onOpen}
        onChange={event => onPick(event.target.value || null)}
      >
        <option value="">{SIM_DAY_PICKER_TODAY}</option>
        {value && !listed ? <option value={value}>{formatShortDate(value)}</option> : null}
        {pastDays.map(day => (
          <option key={day.date} value={day.date} data-recorded={day.recorded ? '1' : '0'} data-rebuilt={day.reconstructed ? '1' : '0'}>
            {dayOptionLabel(day)}
          </option>
        ))}
      </select>
    </label>
  );
}
