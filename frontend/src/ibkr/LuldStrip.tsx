/**
 * The LULD strip above the Level 2 book (ADR 047): each band over its column -- the lower over the bids,
 * the upper over the asks -- with how far the last trade is from it, amber when the price is near one;
 * a limit state's countdown to the pause in red. Nothing outside 09:30-16:00 ET (the bands' hours), so the
 * book keeps its height then. The words are luld.ts's; the hover says whose bands they are.
 */
import { useEffect, useState } from 'react';
import { LULD_LABEL, LULD_TICK_MS, LULD_TIP_TITLE } from '../constantGroups/luld';
import { tipProps } from '../ux';
import { luldStrip, type LuldView } from './luld';

export function LuldStrip({ view, nowMs }: { view: LuldView | null; nowMs?: number }) {
  const [, setTick] = useState(0);
  const counting = nowMs == null && view?.state === 'limit';
  useEffect(() => {
    if (!counting) return undefined;
    const id = window.setInterval(() => setTick(t => t + 1), LULD_TICK_MS);
    return () => window.clearInterval(id);
  }, [counting]);
  const strip = luldStrip(view, nowMs ?? Date.now());
  if (!strip) return null;
  const tip = tipProps(strip.tip, LULD_TIP_TITLE);
  if (strip.center !== null) {
    return (
      <div className={`das-l2-luld das-l2-luld--${strip.tone}`} data-testid="l2-luld" data-state={view?.state} {...tip}>
        <span className="das-l2-luld__center">
          {strip.center}
          {strip.countdown !== null && (
            <span className="das-l2-luld__countdown" style={{ width: `${Math.round(strip.countdown * 100)}%` }}
              aria-hidden="true" />
          )}
        </span>
      </div>
    );
  }
  return (
    <div className={`das-l2-luld das-l2-luld--${strip.tone}${view?.exact && view.tier_sure !== false ? '' : ' das-l2-luld--approx'}`}
      data-testid="l2-luld" data-state={view?.state} {...tip}>
      {([['bid', strip.bid], ['ask', strip.ask]] as const).map(([side, part]) => (
        <span key={side} className={`das-l2-luld__side das-l2-luld__side--${side}${part?.near ? ' das-l2-luld__side--near' : ''}`}
          data-testid={`l2-luld-${side}`}>
          {side === 'bid' && <span className="das-l2-luld__label">{LULD_LABEL}</span>}
          <span className="das-l2-luld__price">{part?.text}</span>
          {part?.pct && <span className="das-l2-luld__pct">{part.pct}</span>}
        </span>
      ))}
    </div>
  );
}
