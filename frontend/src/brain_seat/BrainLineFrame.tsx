/**
 * The brain's Level 2 line on the Trader (ADR 072 decision 10; the twin of Claude's frame): while the stock in this
 * card is the one the brain's lane is on and its Level 2 is up, Level 2 and Time & Sales sit in a purple frame
 * tagged "The brain's line · you share it" -- a tab on the brain's stock costs no extra line. A stock both Claude
 * and the brain are on keeps Claude's frame alone, as it was.
 */
import type { ReactNode } from 'react';
import { useClaudeSeat } from '../claude_seat';
import { useBrainSeat } from './brainSeatStore';
import { BRAIN_LINE_TAG } from './brainWords';
import { BrainMark } from './BrainMark';
import './brainSeat.css';

export function BrainLineFrame({ symbol, children }: { symbol: string | null; children: ReactNode }) {
  const { status } = useBrainSeat();
  const claude = useClaudeSeat().status;
  const sym = symbol ? symbol.toUpperCase() : null;
  const claudes = Boolean(sym && claude?.line.depth && claude.line.symbol === sym);
  const mine = Boolean(sym && !claudes && status?.lane.depth && status.lane.symbol === sym);
  // Always the same wrapper, so Level 2 and Time & Sales never remount (and reopen their lines) when the frame
  // comes or goes: unframed it is `display: contents`, no box of its own.
  return (
    <div className={mine ? 'brain-line-frame' : 'brain-line-frame brain-line-frame--off'}
      data-testid={mine ? 'brain-line-frame' : undefined}>
      {mine ? <span className="brain-line-frame__tag"><BrainMark size={12} />{BRAIN_LINE_TAG}</span> : null}
      {children}
    </div>
  );
}
