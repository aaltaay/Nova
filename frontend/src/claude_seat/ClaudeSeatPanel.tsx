/**
 * The panel under the Claude pill (ADR 068, the approved design's 2): what Claude sees and why, its order, its
 * line, its day, its reflexes, and the operator's two buttons -- Take Claude's line (or give it back) and Stop
 * Claude, which asks first. A refused button says why under it.
 */
import { useState } from 'react';
import { confirmApp } from '../ux';
import { giveClaudeLineBack, stopClaude, takeClaudesLine } from './claudeSeatApi';
import { applyClaudeSeat } from './claudeSeatStore';
import { TickerLink } from '../components/TickerLink';
import { buySetRow, checkedIn, etClock, fmtPrice, fmtQty, lineRow, lockWhy, todayRow } from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import type { ClaudeSeatStatus } from './types';

const EVENTS_SHOWN = 4;

export const CLAUDE_STOP_CONFIRM = "Sell Claude's shares and stop it?";

export function ClaudeSeatPanel({ status }: { status: ClaudeSeatStatus }) {
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const run = async (act: () => Promise<ClaudeSeatStatus | null>) => {
    setBusy(true);
    setWhy(null);
    try {
      applyClaudeSeat(await act());
    } catch (err) {
      setWhy(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    const yes = await confirmApp({
      title: 'Stop Claude',
      message: `${CLAUDE_STOP_CONFIRM} Its working orders are cancelled and its Paper shares sold at market; the line is yours.`,
      confirmLabel: 'Stop Claude',
      tone: 'danger',
    });
    if (yes) await run(stopClaude);
  };
  const buySet = buySetRow(status);
  const seen = checkedIn(status);
  const position = status.positions[0];
  return (
    <div className="claude-panel" role="dialog" aria-label="Claude's seat" data-testid="claude-panel">
      <div className="claude-panel__head">
        <ClaudeMark size={24} />
        <div>
          <div className="claude-panel__title">{status.text}</div>
          <div className="claude-panel__sub">Paper only{seen ? ` · ${seen}` : ''}</div>
        </div>
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
      <div className="claude-panel__btns">
        {status.yielded ? (
          <button type="button" className="claude-btn" disabled={busy} data-why={lockWhy(busy, true)} data-testid="claude-give-back"
            onClick={() => { void run(giveClaudeLineBack); }}>
            Give Claude its line back
          </button>
        ) : (
          <button type="button" className="claude-btn claude-btn--warn" disabled={busy || !status.on}
            data-why={lockWhy(busy, status.on)} data-testid="claude-take-line" onClick={() => { void run(takeClaudesLine); }}>
            Take Claude's line
          </button>
        )}
        <button type="button" className="claude-btn claude-btn--stop" disabled={busy || !status.on}
          data-why={lockWhy(busy, status.on)} data-testid="claude-stop" onClick={() => { void stop(); }}>
          Stop Claude
        </button>
      </div>
      <div className="claude-panel__help">
        <div>{status.yielded
          ? 'Claude takes a free line again and may trade.'
          : 'The line is yours. I make no new trades; an open trade keeps its stop.'}</div>
        <div>Cancels my orders and sells my shares now.</div>
      </div>
      {why ? <p className="claude-panel__warn" role="alert" data-testid="claude-panel-why">{why}</p> : null}
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
