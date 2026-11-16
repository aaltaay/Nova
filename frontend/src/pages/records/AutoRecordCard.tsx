/**
 * The recording switch's card on Records (operator ask 2026-10-14; ADR 071): On, Off for today, Off -- what
 * the lanes record now, and what turning it off stops. Nova records a stock while a lane watches it: yours,
 * Claude's seat's or the bots'. Every state comes from `/api/ibkr/status` `lanes` and `recording_switch`;
 * with no switch in the status the switch is locked and says why.
 */
import { LANE_OWNER_WORDS } from '../../capture/constants';
import type { LaneOwner, LaneRecording } from '../../ibkr';
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
  RECORDS_AUTO_SUB,
  RECORDS_AUTO_SWITCH_LABEL,
  RECORDS_AUTO_TITLE,
  RECORDS_AUTO_UNAVAILABLE,
  RECORDS_ON_NOTHING,
  RECORDS_TURNING_OFF_NOTHING,
  recordsOnRecording,
  recordsSwitchError,
  recordsTurningOffStops,
} from './recordsConstants';
import { etMinute, hm, joinWords, todayEasternDate } from './recordsModel';
import type { AutoRecordSwitchControl } from './useAutoRecordSwitch';

interface Props {
  rec: LaneRecording;
  nowSec: number;
  control: AutoRecordSwitchControl;
}

/** "04:00 ET tomorrow" (or "04:00 ET" when it turns back on later today). */
function untilWords(until: number | null, nowSec: number): string {
  if (until == null) return '04:00 ET tomorrow';
  const sameDay = todayEasternDate(new Date(until * 1000)) === todayEasternDate(new Date(nowSec * 1000));
  return `${hm(etMinute(until))} ET${sameDay ? '' : ' tomorrow'}`;
}

/** "XLAB (your lane), AISP (the bots' lane)". */
export function laneSymbolsWords(rec: LaneRecording): string {
  return joinWords(rec.symbols.map(s => {
    const owners = (rec.owners[s] ?? []).map((o: LaneOwner) => LANE_OWNER_WORDS[o]);
    return owners.length ? `${s} (${joinWords(owners)})` : s;
  }));
}

export function AutoRecordCard({ rec, nowSec, control }: Props) {
  const sw = rec.switch;
  const envHolds = sw?.source === 'env';
  const mode = sw?.mode ?? null;
  const lockWhy = !sw ? RECORDS_AUTO_UNAVAILABLE : envHolds ? RECORDS_AUTO_ENV : control.busy ? RECORDS_AUTO_BUSY : null;
  const held = rec.symbols;

  let status: string | null = null;
  if (envHolds) status = RECORDS_AUTO_ENV;
  else if (mode === 'off_today') status = RECORDS_AUTO_OFF_TODAY(untilWords(sw?.until ?? null, nowSec));
  else if (mode === 'off') status = RECORDS_AUTO_OFF;
  else if (mode === 'on') status = held.length ? recordsOnRecording(laneSymbolsWords(rec)) : RECORDS_ON_NOTHING;

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
        {rec.error && <p className="records-ar__line records-warn">{recordsSwitchError(rec.error)}</p>}
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
