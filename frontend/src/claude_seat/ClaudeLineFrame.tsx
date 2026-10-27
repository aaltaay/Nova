/**
 * Claude's Level 2 line on the Trader (ADR 068, the approved design's 4): while the stock in this card is the one
 * Claude holds its line on, Level 2 and Time & Sales sit in a violet frame tagged "Claude's line · you share it" --
 * a tab on Claude's stock costs no extra line.
 */
import type { ReactNode } from 'react';
import { useClaudeSeat } from './claudeSeatStore';
import { ClaudeMark } from './ClaudeMark';
import './claudeSeat.css';

export function ClaudeLineFrame({ symbol, children }: { symbol: string | null; children: ReactNode }) {
  const { status } = useClaudeSeat();
  const mine = Boolean(symbol && status?.line.depth && status.line.symbol === symbol.toUpperCase());
  // Always the same wrapper, so Level 2 and Time & Sales never remount (and reopen their lines) when the frame
  // comes or goes: unframed it is `display: contents`, no box of its own.
  return (
    <div className={mine ? 'claude-line-frame' : 'claude-line-frame claude-line-frame--off'}
      data-testid={mine ? 'claude-line-frame' : undefined}>
      {mine ? <span className="claude-line-frame__tag"><ClaudeMark size={12} />Claude's line · you share it</span> : null}
      {children}
    </div>
  );
}
