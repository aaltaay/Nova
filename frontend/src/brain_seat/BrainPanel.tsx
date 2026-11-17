/**
 * The panel under the brain's pill (ADR 072; approved mockup brain-switches v1 section 2, the left panel): its head
 * with the big On / Off switch -- the one write --, the brain's last note, its lane, position, day against the day
 * stop and limits (with the way to Settings), what it is reading now, and what Off does. A refused press and a read
 * that failed are said in words above the foot, never swallowed.
 */
import { TickerLink } from '../components/TickerLink';
import { useSettingsOptional } from '../settings';
import {
  BRAIN_NOT_RUNNING_TIP,
  BRAIN_PANEL_LABEL,
  BRAIN_PNL_UNKNOWN,
  BRAIN_READING_HEAD,
  BRAIN_READING_LANE,
  BRAIN_READING_LEVEL1,
  BRAIN_SETTINGS_LINK,
  BRAIN_SWITCH_OFF,
  BRAIN_SWITCH_ON,
  brainHelp,
  brainLaneRow,
  brainLimitsRow,
  brainNoteHead,
  brainPillTitle,
  brainPositionRow,
  brainSubLine,
  brainTodayRow,
  type BrainPillWords,
  type BrainSymbolWords,
} from './brainWords';
import { BrainMark } from './BrainMark';
import { BrainSwitchButton, type BrainSwitchPress } from './BrainSwitch';
import type { BrainSeatStatus } from './types';

/** Words around one ticker, the ticker a door to its Trader tab. */
function SymbolWords({ words }: { words: BrainSymbolWords }) {
  return (
    <span>
      {words.before}
      {words.symbol ? <b><TickerLink symbol={words.symbol} look="own" /></b> : null}
      {words.after}
    </span>
  );
}

export function BrainPanel({ status, words, press, readError }: {
  status: BrainSeatStatus; words: BrainPillWords; press: BrainSwitchPress; readError: string | null;
}) {
  const settings = useSettingsOptional();
  const today = brainTodayRow(status);
  const limits = brainLimitsRow(status);
  const help = brainHelp(status);
  return (
    <div className="brain-panel" role="dialog" aria-label={BRAIN_PANEL_LABEL} data-testid="brain-panel">
      <div className="brain-panel__head">
        <BrainMark size={26} />
        <div className="brain-panel__grow">
          <div className="brain-panel__title" data-testid="brain-panel-title">{brainPillTitle(words)}</div>
          <div className="brain-panel__sub">{brainSubLine(status.venue)}</div>
        </div>
        <span className="brain-panel__switch">
          {status.on ? BRAIN_SWITCH_ON : BRAIN_SWITCH_OFF}
          <BrainSwitchButton status={status} press={press} big />
        </span>
      </div>
      {status.note ? (
        <div className="brain-panel__say" data-testid="brain-panel-note">
          <b>{brainNoteHead(status.note.at)}</b>
          {status.note.text}
        </div>
      ) : null}
      <div className="brain-panel__rows">
        <div className="brain-panel__row" data-testid="brain-panel-lane" title={status.lane.why ?? undefined}>
          <span>Lane</span>
          <SymbolWords words={brainLaneRow(status.lane)} />
        </div>
        <div className="brain-panel__row" data-testid="brain-panel-position">
          <span>Position</span>
          <SymbolWords words={brainPositionRow(status)} />
        </div>
        <div className="brain-panel__row" data-testid="brain-panel-today">
          <span>Today</span>
          <span>
            {today.pnl
              ? <span className={`brain-num is-${today.pnl.tone}`}>{today.pnl.text}</span>
              : BRAIN_PNL_UNKNOWN}
            {today.meter !== null ? (
              <span className="brain-panel__meter" data-testid="brain-panel-meter" aria-hidden="true">
                <i style={{ width: `${Math.round(today.meter * 100)}%` }} />
              </span>
            ) : null}
            {today.stop ? <span className="brain-panel__muted">{today.stop}</span> : null}
          </span>
        </div>
        <div className="brain-panel__row" data-testid="brain-panel-limits">
          <span>Limits</span>
          <span>
            {limits.map(l => (
              <span key={l.unit}><span className="brain-num">{l.figure}</span> {l.unit} · </span>
            ))}
            {settings ? (
              <button type="button" className="brain-panel__link" data-testid="brain-panel-settings"
                onClick={() => settings.openSettings('loss_limits')}>
                {BRAIN_SETTINGS_LINK}
              </button>
            ) : <span className="brain-panel__link">{BRAIN_SETTINGS_LINK}</span>}
          </span>
        </div>
      </div>
      {status.reading.length ? (
        <div className="brain-panel__reading" data-testid="brain-panel-reading">
          <div className="brain-panel__reading-head">{BRAIN_READING_HEAD}</div>
          {status.reading.map((r, i) => (
            <div className="brain-panel__read" key={`${r.symbol}-${i}`}>
              <b><TickerLink symbol={r.symbol} look="own" /></b>
              <span>{r.text}</span>
              <span className={r.source === 'lane' ? 'brain-panel__tag is-lane' : 'brain-panel__tag'}>
                {r.source === 'lane' ? BRAIN_READING_LANE : BRAIN_READING_LEVEL1}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {status.on && status.connected === false ? (
        <p className="brain-panel__warn" role="status" data-testid="brain-panel-not-running">{BRAIN_NOT_RUNNING_TIP}</p>
      ) : null}
      {status.read_error ? <p className="brain-panel__warn" role="status">{status.read_error}</p> : null}
      {readError ? <p className="brain-panel__warn" role="status" data-testid="brain-panel-read-error">{readError}</p> : null}
      {press.why ? <p className="brain-panel__warn" role="alert" data-testid="brain-panel-why">{press.why}</p> : null}
      <div className="brain-panel__help" data-testid="brain-panel-help">
        {help.lead ? <b>{help.lead} </b> : null}
        {help.text}
      </div>
    </div>
  );
}
