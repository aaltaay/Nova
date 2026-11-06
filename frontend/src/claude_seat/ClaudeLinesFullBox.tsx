/**
 * A 3rd Level 2 while Claude holds one (ADR 068, the approved design's 6): the panel says all 3 lines are in use,
 * whose they are, and offers the one button that frees one now -- Take Claude's line. Never a silent block.
 */
import { useState } from 'react';
import { takeClaudesLine } from './claudeSeatApi';
import { applyClaudeSeat, useClaudeSeat } from './claudeSeatStore';
import { lockWhy } from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import './claudeSeat.css';

export const CLAUDE_LINES_FULL = 'All 3 Level 2 lines are in use';
export const CLAUDE_LINES_WAYS = 'Close one of yours and this one opens by itself. Or take Claude\'s line: Claude '
  + 'makes no new trades, and its open trade keeps its stop.';

export function ClaudeLinesFullBox({ message }: { message: string }) {
  const { status } = useClaudeSeat();
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const yours = status?.line.desk_lines ?? [];
  const claude = status?.line.symbol ?? null;
  const take = async () => {
    setBusy(true);
    setWhy(null);
    try {
      applyClaudeSeat(await takeClaudesLine());
    } catch (err) {
      setWhy(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="claude-lines-full" role="status" data-testid="claude-lines-full">
      <ClaudeMark size={22} />
      <p className="claude-lines-full__title">{CLAUDE_LINES_FULL}</p>
      {yours.length || claude ? (
        <div className="claude-lines-full__chips">
          {yours.map(s => <span key={s} className="claude-chip">{s} · you</span>)}
          {claude ? <span className="claude-chip claude-chip--claude">{claude} · Claude</span> : null}
        </div>
      ) : null}
      {/* The chips say whose lines they are; without them, the backend's own sentence says it. */}
      <p className="claude-lines-full__msg">{yours.length || claude ? CLAUDE_LINES_WAYS : message}</p>
      <button type="button" className="claude-btn claude-btn--warn" disabled={busy || !status?.on}
        data-why={lockWhy(busy, status?.on === true)} data-testid="claude-lines-full-take" onClick={() => { void take(); }}>
        Take Claude's line
      </button>
      {why ? <p className="claude-panel__warn" role="alert">{why}</p> : null}
    </div>
  );
}
