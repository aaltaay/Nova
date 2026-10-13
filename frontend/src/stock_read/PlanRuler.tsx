/** The plan's ruler (stop -> entry -> target 1 -> target 2 (#845), what stands between, where the price is now; a
 * short's runs from its buy stop down, ADR 048) and its checks, one glyph each: ✓ for it, ✗ against it, ! caution,
 * ? unknown. The price tick is the tab's tape, not the read's 5 s price (operator report 2026-10-13: "way too
 * delayed"), and glides to each new price. */
import { useLayoutEffect, useState, type CSSProperties } from 'react';
import { tipProps } from '../ux';
import { STATE_WORDS } from './constants';
import { checkGlyph, fmtPx, rulerLayout } from './planMath';
import type { PlanCheck, StockPlan } from './types';
import { useTapePrice } from './useTapePrice';

/** The price tick's track: the ruler's whole width slid to `pct`, so the tick moves on the compositor (a transform
 * transitions there; `left` would lay out the page on every tick, #707). */
export function rulerTrack(pct: number): CSSProperties {
  return { transform: `translateX(${pct}%)` };
}

/** A bar from `s[0]` to `s[1]` (percent of the ruler) as a transform of a full-width bar, so it glides with the
 * tick. */
export function rulerGlide(s: [number, number]): CSSProperties {
  return { transform: `translateX(${s[0]}%) scaleX(${(s[1] - s[0]) / 100})` };
}

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

export function PlanRuler({ plan, symbol, price: readPrice }: {
  plan: StockPlan;
  symbol: string;
  /** The read's price, until the tape has one. */
  price: number | null;
}) {
  const [ref, width] = useWidth();
  const price = useTapePrice(symbol, readPrice);
  const lay = rulerLayout(plan, price, width);
  if (!lay) return null;
  const short = plan.side === 'short';
  const last = plan.target2 != null ? (short ? 'cover 2' : 'target 2') : (short ? 'the cover target' : 'the target');
  const nowTip = price === null ? null : lay.now?.edge === 'low'
    ? `Last ${fmtPx(price)}: ${short ? 'over the buy stop' : 'under the stop'}`
    : lay.now?.edge === 'high' ? `Last ${fmtPx(price)}: ${short ? 'under' : 'over'} ${last}`
      : `Last ${fmtPx(price)}`;
  // Target 1's part solid; with a target 2, the rest's part runs on, fainter (#845).
  const t1 = lay.target1Pct ?? lay.targetPct;
  return (
    <div ref={ref} className="sr-ruler" data-testid="stock-read-ruler" aria-hidden="true">
      <span className="sr-ruler__risk" style={{ left: `${lay.stopPct}%`, width: `${lay.entryPct - lay.stopPct}%` }} />
      <span className="sr-ruler__reward" style={{ left: `${lay.entryPct}%`, width: `${t1 - lay.entryPct}%` }} />
      {lay.target1Pct !== null && (
        <span className="sr-ruler__reward sr-ruler__reward--rest" data-testid="stock-read-ruler-rest"
          style={{ left: `${t1}%`, width: `${lay.targetPct - t1}%` }} />
      )}
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
      {lay.target1Pct !== null && <span className="sr-ruler__end sr-ruler__end--target" style={{ left: `${lay.target1Pct}%` }} />}
      <span className="sr-ruler__end sr-ruler__end--target" style={{ left: `${lay.targetPct}%` }} />
      <span className="sr-ruler__entry" style={{ left: `${lay.entryPct}%` }} />
      {lay.now && (
        <span className="sr-ruler__track" style={rulerTrack(lay.now.pct)}>
          <span className={`sr-ruler__now${lay.now.edge ? ` sr-ruler__now--${lay.now.edge}` : ''}`} {...tipProps(nowTip)} />
        </span>
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
