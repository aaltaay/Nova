/**
 * A pane's words while no lane is on its stock (ADR 071), in the pane's own empty-state look. A click (or Enter)
 * on them brings your lane here: the stock's Level 2 and Time & Sales in this window ask for it now (laneWait.ts).
 */
import type { KeyboardEvent } from 'react';
import { bringLane } from './laneWait';

export function LaneWaitText({ symbol, text, className, testId }: {
  symbol: string; text: string; className: string; testId: string;
}) {
  const bring = () => bringLane(symbol);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    bring();
  };
  return (
    <div className={`${className} lane-wait`} data-testid={testId} role="button" tabIndex={0}
      onClick={bring} onKeyDown={onKey}>
      {text}
    </div>
  );
}
