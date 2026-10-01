/** The plan's ruler (stop -> entry -> target, what stands between, where the price is now) and its
 * checks, one glyph each: ✓ for it, ✗ against it, ! caution, ? unknown. */
import { useLayoutEffect, useState } from 'react';
import { tipProps } from '../ux';
import { STATE_WORDS } from './constants';
import { checkGlyph, fmtPx, rulerLayout } from './planMath';
import type { PlanCheck, StockPlan } from './types';

/** The element's width, followed as it resizes (a callback ref: the ruler is absent while a plan has no
 * levels). */
export function useWidth(): [(el: HTMLDivElement | null) => void, number | null] {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  useLayoutEffect(() => {
    if (!el) return undefined;
    setWidth(el.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setWidth(e.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return [setEl, width];
}

export function PlanRuler({ plan, price }: { plan: StockPlan; price: number | null }) {
  const [ref, width] = useWidth();
  const lay = rulerLayout(plan, price, width);
  if (!lay) return null;
  const nowTip = price === null ? null : lay.now?.edge === 'low'
    ? `Last ${fmtPx(price)}: under the stop`
    : lay.now?.edge === 'high' ? `Last ${fmtPx(price)}: over the target` : `Last ${fmtPx(price)}`;
  return (
    <div ref={ref} className="sr-ruler" data-testid="stock-read-ruler" aria-hidden="true">
      <span className="sr-ruler__risk" style={{ left: `${lay.stopPct}%`, width: `${lay.entryPct - lay.stopPct}%` }} />
      <span className="sr-ruler__reward" style={{ left: `${lay.entryPct}%`, width: `${lay.targetPct - lay.entryPct}%` }} />
      {lay.marks.map(m => (
        <span
          key={`${m.kind}-${m.label}`}
          className={`sr-ruler__mark sr-ruler__mark--${m.kind}`}
          style={{ left: `${m.pct}%` }}
        >
          {m.showLabel && <span className="sr-ruler__mark-label">{m.label}</span>}
        </span>
      ))}
      <span className="sr-ruler__end sr-ruler__end--stop" style={{ left: `${lay.stopPct}%` }} />
      <span className="sr-ruler__end sr-ruler__end--target" style={{ left: `${lay.targetPct}%` }} />
      <span className="sr-ruler__entry" style={{ left: `${lay.entryPct}%` }} />
      {lay.now && (
        <span
          className={`sr-ruler__now${lay.now.edge ? ` sr-ruler__now--${lay.now.edge}` : ''}`}
          style={{ left: `${lay.now.pct}%` }}
          {...tipProps(nowTip)}
        />
      )}
    </div>
  );
}

export function PlanChecks({ plan }: { plan: StockPlan }) {
  return <CheckList checks={plan.checks} />;
}

/** The checks, one glyph each (the plan's, or the trade you hold's). */
export function CheckList({ checks: all }: { checks: PlanCheck[] }) {
  // The risk against the cap is already under Risk / sh.
  const checks = all.filter(c => c.id !== 'risk');
  if (checks.length === 0) return null;
  return (
    <ul className="sr-checks" data-testid="stock-read-checks">
      {checks.map(c => (
        <li key={`${c.id}-${c.text}`} className={`sr-check sr-check--${c.state}`} {...tipProps(c.text, STATE_WORDS[c.state])}>
          <span className="sr-check__glyph" aria-label={STATE_WORDS[c.state]}>{checkGlyph(c.state)}</span>
          {c.text}
        </li>
      ))}
    </ul>
  );
}
