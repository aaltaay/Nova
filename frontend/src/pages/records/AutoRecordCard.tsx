/**
 * Auto-record's card on Records (operator ask 2026-10-14): the switch -- On,
 * Off for today, Off -- which window is open and what it holds, its windows
 * drawn on the day's clock with a line at now, and what turning it off stops.
 * Every state comes from `/api/ibkr/status` `auto_record`; with no switch in the
 * status the switch is locked and says why.
 */
import type { ReactNode } from 'react';
import type { AutoRecordStatus, AutoRecordWindows } from '../../ibkr/types';
import { setupLabel, setupShort } from '../../setups';
import { whyProps } from '../../ux/whyTip';
import {
  RECORDS_AUTO_BUSY,
  RECORDS_AUTO_ENV,
  RECORDS_AUTO_FAILED,
  RECORDS_AUTO_FINE_OFF,
  RECORDS_AUTO_FINE_OFF_TAIL,
  RECORDS_AUTO_FINE_TODAY,
  RECORDS_AUTO_FINE_TODAY_TAIL,
  RECORDS_AUTO_MODES,
  RECORDS_AUTO_OFF,
  RECORDS_AUTO_OFF_TODAY,
  RECORDS_AUTO_OPEN_NOW,
  RECORDS_AUTO_SUB,
  RECORDS_AUTO_SWITCH_LABEL,
  RECORDS_AUTO_TITLE,
  RECORDS_AUTO_UNAVAILABLE,
  RECORDS_CLOSED_TODAY,
  RECORDS_HOLDING_NONE,
  RECORDS_LEADERS_LABEL,
  RECORDS_NOW,
  RECORDS_TURNING_OFF_NOTHING,
  recordsHolding,
  recordsOpensAt,
  recordsOpenWindows,
  recordsSwitchError,
  recordsTurningOffStops,
  recordsWindowTitle,
} from './recordsConstants';
import { AXIS_DEFAULT, etMinute, hm, joinWords, minutesOf, pct, todayEasternDate, type Axis } from './recordsModel';
import type { AutoRecordSwitchControl } from './useAutoRecordSwitch';

interface Props {
  auto: AutoRecordStatus | null | undefined;
  nowSec: number;
  control: AutoRecordSwitchControl;
}

interface WindowRow {
  key: string;
  label: string;
  /** The live row's setup names, for the "Open now" line. */
  long: string;
  start: string;
  end: string;
  open: boolean;
}

/** One row per arming window (setups sharing a window share a row), longest first, then the leaders. */
export function windowRows(windows: AutoRecordWindows): WindowRow[] {
  const groups = new Map<string, WindowRow & { setups: string[] }>();
  for (const w of windows.setups.by_setup) {
    const key = `${w.start}-${w.end}`;
    const row = groups.get(key) ?? { key, label: '', long: '', start: w.start, end: w.end, open: false, setups: [] };
    row.setups.push(w.setup);
    row.open = row.open || w.open;
    groups.set(key, row);
  }
  const rows = [...groups.values()]
    .sort((a, b) => (minutesOf(b.end) - minutesOf(b.start)) - (minutesOf(a.end) - minutesOf(a.start)))
    .map(({ setups, ...row }) => ({
      ...row,
      label: setups.length === 1 ? setupLabel(setups[0]) : setups.map(setupShort).join(', '),
      long: joinWords(setups.map(s => setupLabel(s).toLowerCase())),
    }));
  const leaders = windows.leaders;
  rows.push({ key: 'leaders', label: RECORDS_LEADERS_LABEL, long: RECORDS_LEADERS_LABEL.toLowerCase(),
    start: leaders.start, end: leaders.end, open: leaders.open });
  return rows;
}

function scheduleAxis(rows: readonly WindowRow[]): Axis {
  const lo = Math.min(AXIS_DEFAULT.t0, ...rows.map(r => minutesOf(r.start)));
  const hi = Math.max(AXIS_DEFAULT.t1, ...rows.map(r => minutesOf(r.end)));
  return { t0: Math.floor(lo / 60) * 60, t1: Math.ceil(hi / 60) * 60 };
}

/** The open window's words: "the 5-minute flat top window, until 15:30". */
function openLine(rows: readonly WindowRow[]): { labels: string; until: string } | null {
  const open = rows.filter(r => r.open);
  if (!open.length) return null;
  const until = open.reduce((m, r) => Math.max(m, minutesOf(r.end)), 0);
  const names = open.map(r => r.long);
  return { labels: `the ${joinWords(names)} ${open.length === 1 ? 'window' : 'windows'}`, until: hm(until) };
}

/** "04:00 ET tomorrow" (or "04:00 ET" when it turns back on later today). */
function untilWords(until: number | null, nowSec: number): string {
  if (until == null) return '04:00 ET tomorrow';
  const sameDay = todayEasternDate(new Date(until * 1000)) === todayEasternDate(new Date(nowSec * 1000));
  return `${hm(etMinute(until))} ET${sameDay ? '' : ' tomorrow'}`;
}

export function AutoRecordCard({ auto, nowSec, control }: Props) {
  const sw = auto?.switch;
  const envHolds = sw?.source === 'env';
  const mode = sw?.mode ?? null;
  const lockWhy = !sw ? RECORDS_AUTO_UNAVAILABLE : envHolds ? RECORDS_AUTO_ENV : control.busy ? RECORDS_AUTO_BUSY : null;
  const rows = auto?.windows ? windowRows(auto.windows) : [];
  const axis = scheduleAxis(rows);
  const nowMin = etMinute(nowSec);
  const held = auto?.symbols ?? [];
  const open = openLine(rows);
  const firstStart = rows.length ? Math.min(...rows.map(r => minutesOf(r.start))) : null;

  let status: ReactNode = null;
  if (envHolds) status = RECORDS_AUTO_ENV;
  else if (mode === 'off_today') status = RECORDS_AUTO_OFF_TODAY(untilWords(sw?.until ?? null, nowSec));
  else if (mode === 'off') status = RECORDS_AUTO_OFF;
  else if (mode === 'on' && open) {
    status = (<>
      <b className="records-ar__open">{RECORDS_AUTO_OPEN_NOW}</b>{recordsOpenWindows(open.labels, open.until)}
      {held.length ? recordsHolding(joinWords(held)) : RECORDS_HOLDING_NONE}
    </>);
  } else if (mode === 'on') {
    status = firstStart != null && nowMin < firstStart ? recordsOpensAt(hm(firstStart)) : RECORDS_CLOSED_TODAY;
  }
  const ticks = [axis.t0, 9 * 60 + 30, 12 * 60, 14 * 60, axis.t1].filter((m, i, all) =>
    m >= axis.t0 && m <= axis.t1 && all.indexOf(m) === i);

  return (
    <section className="records-card records-ar" aria-label={RECORDS_AUTO_TITLE} data-testid="records-auto-record">
      <header className="records-card__head">
        <h3 className="records-card__title">{RECORDS_AUTO_TITLE}</h3>
        <span className="records-card__sub">{RECORDS_AUTO_SUB}</span>
      </header>
      <div className="records-ar__body">
        <div className="records-seg" role="group" aria-label={RECORDS_AUTO_SWITCH_LABEL} data-testid="records-auto-switch">
          {RECORDS_AUTO_MODES.map(({ mode: m, label }) => {
            const on = (control.busy ?? mode) === m;
            const locked = lockWhy != null;
            return (
              <button key={m} type="button" className={`records-seg__opt${on ? ' is-on' : ''}${m !== 'on' && on ? ' is-off' : ''}`}
                aria-pressed={on} disabled={locked} {...whyProps(locked, lockWhy)}
                data-testid={`records-auto-${m}`}
                onClick={() => { if (!on) void control.setMode(m); }}>
                {label}
              </button>
            );
          })}
        </div>
        {status && <p className="records-ar__line" data-testid="records-auto-line">{status}</p>}
        {control.error && (
          <p className="records-ar__line records-warn" role="alert">{RECORDS_AUTO_FAILED} {control.error}</p>
        )}
        {sw?.error && <p className="records-ar__line records-warn">{recordsSwitchError(sw.error)}</p>}
        {auto?.windows?.setups.error && <p className="records-ar__line records-warn">{auto.windows.setups.error}</p>}
        {rows.length > 0 && (
          <div className="records-sched" data-testid="records-auto-windows">
            {rows.map(r => (
              <div key={r.key} className="records-sched__row" title={recordsWindowTitle(r.label, r.start, r.end, r.open)}>
                <span className="records-sched__label">{r.label}</span>
                <div className="records-sched__track">
                  <div className={`records-sched__win${r.open ? ' is-open' : ''}`} style={{
                    left: `${pct(minutesOf(r.start), axis)}%`,
                    width: `${pct(minutesOf(r.end), axis) - pct(minutesOf(r.start), axis)}%`,
                  }} />
                </div>
              </div>
            ))}
            <div className="records-sched__axis">
              {ticks.map(m => <span key={m} style={{ left: `${pct(m, axis)}%` }}>{hm(m)}</span>)}
            </div>
            {nowMin >= axis.t0 && nowMin <= axis.t1 && (
              <div className="records-sched__now"
                style={{ left: `calc(var(--label-w) + (100% - var(--label-w)) * ${pct(nowMin, axis) / 100})` }}>
                <span>{RECORDS_NOW}</span>
              </div>
            )}
          </div>
        )}
        {mode === 'on' && !envHolds && (
          <p className="records-ar__line">
            {held.length ? recordsTurningOffStops(joinWords(held)) : RECORDS_TURNING_OFF_NOTHING}
          </p>
        )}
      </div>
      <p className="records-ar__fine">
        <b>{RECORDS_AUTO_FINE_TODAY}</b>{RECORDS_AUTO_FINE_TODAY_TAIL}
        <b>{RECORDS_AUTO_FINE_OFF}</b>{RECORDS_AUTO_FINE_OFF_TAIL}
      </p>
    </section>
  );
}
