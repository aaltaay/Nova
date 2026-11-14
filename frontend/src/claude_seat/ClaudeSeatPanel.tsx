/**
 * The panel under the Claude pill (ADR 068, the approved design's 2; ADR 072, mockup brain-switches v1 section 2):
 * what Claude sees and why, its order, its line, its day, its reflexes and events, and in its head the big On / Off
 * switch -- the one write. The switch replaces Stop Claude and Take Claude's line: Off sells nothing, it hands
 * Claude's open trade to you. A refused press is said under the rows in Nova's words.
 */
import { TickerLink } from '../components/TickerLink';
import {
  CLAUDE_SWITCH_OFF,
  CLAUDE_SWITCH_OFF_HELP,
  CLAUDE_SWITCH_ON,
  CLAUDE_SWITCH_ON_HELP,
  buySetRow,
  checkedIn,
  etClock,
  fmtPrice,
  fmtQty,
  lineRow,
  todayRow,
} from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import { ClaudeSwitchButton, type ClaudeSwitchPress } from './ClaudeSwitch';
import type { ClaudeSeatStatus } from './types';

const EVENTS_SHOWN = 4;

export function ClaudeSeatPanel({ status, press }: { status: ClaudeSeatStatus; press: ClaudeSwitchPress }) {
  const buySet = buySetRow(status);
  const seen = checkedIn(status);
  const position = status.positions[0];
  const sw = status.switch;
  return (
    <div className="claude-panel" role="dialog" aria-label="Claude's seat" data-testid="claude-panel">
      <div className="claude-panel__head">
        <ClaudeMark size={24} />
        <div className="claude-panel__grow">
          <div className="claude-panel__title">{status.text}</div>
          <div className="claude-panel__sub">Paper only{seen ? ` · ${seen}` : ''}</div>
        </div>
        {sw ? (
          <span className="claude-panel__switch">
            {sw.on ? CLAUDE_SWITCH_ON : CLAUDE_SWITCH_OFF}
            <ClaudeSwitchButton sw={sw} press={press} big />
          </span>
        ) : null}
      </div>
      {status.note ? (
        <div className="claude-panel__note" data-testid="claude-panel-note">
          <b>Claude, {etClock(status.note.at)}</b>
          {status.note.text}
        </div>
      ) : null}
      <div className="claude-panel__row"><span>My line</span><span>{lineRow(status)}</span></div>
      {position ? (
        <div className="claude-panel__row">
          <span>Position</span>
          <span>{fmtQty(position.qty)} <TickerLink symbol={position.symbol} />{position.mark !== null ? ` · now ${fmtPrice(position.mark)}` : ''}</span>
        </div>
      ) : null}
      {buySet ? <div className="claude-panel__row"><span>Buy set</span><span>{buySet}</span></div> : null}
      <div className="claude-panel__row"><span>Today</span><span>{todayRow(status)}</span></div>
      {status.reflexes.length ? (
        <div className="claude-panel__reflexes" data-testid="claude-panel-reflexes">
          <span>Reflexes</span>
          <ul>{status.reflexes.map(r => <li key={r.id}>{r.text}</li>)}</ul>
        </div>
      ) : null}
      {status.read_error ? <p className="claude-panel__warn" role="status">{status.read_error}</p> : null}
      {press.why ? <p className="claude-panel__warn" role="alert" data-testid="claude-panel-why">{press.why}</p> : null}
      {sw ? (
        <div className="claude-panel__help" data-testid="claude-panel-help">
          {sw.on ? CLAUDE_SWITCH_OFF_HELP : (sw.why_not_on?.error ?? CLAUDE_SWITCH_ON_HELP)}
        </div>
      ) : null}
      {status.events.length ? (
        <div className="claude-panel__events">
          {status.events.slice(0, EVENTS_SHOWN).map(e => (
            <div key={`${e.at}-${e.kind}`}><b>{etClock(e.at, true)}</b> {e.text}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
