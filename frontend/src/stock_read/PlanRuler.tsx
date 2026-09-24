/** The plan's ruler (stop -> entry -> target, what stands between, where the price is now) and its
 * checks, one glyph each: ✓ for it, ✗ against it, ! caution, ? unknown. */
import { tipProps } from '../ux';
import { STATE_WORDS } from './constants';
import { checkGlyph, fmtPx, rulerLayout } from './planMath';
import type { StockPlan } from './types';

export function PlanRuler({ plan, price }: { plan: StockPlan; price: number | null }) {
  const lay = rulerLayout(plan, price);
  if (!lay) return null;
  const nowTip = price === null ? null : lay.now?.edge === 'low'
    ? `Last ${fmtPx(price)}: under the stop`
    : lay.now?.edge === 'high' ? `Last ${fmtPx(price)}: over the target` : `Last ${fmtPx(price)}`;
  return (
    <div className="sr-ruler" data-testid="stock-read-ruler" aria-hidden="true">
      <span className="sr-ruler__risk" style={{ left: `${lay.stopPct}%`, width: `${lay.entryPct - lay.stopPct}%` }} />
      <span className="sr-ruler__reward" style={{ left: `${lay.entryPct}%`, width: `${lay.targetPct - lay.entryPct}%` }} />
      {lay.marks.map(m => (
        <span
          key={`${m.kind}-${m.label}`}
          className={`sr-ruler__mark sr-ruler__mark--${m.kind}`}
          style={{ left: `${m.pct}%` }}
        >
          <span className="sr-ruler__mark-label">{m.label}</span>
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
  // The risk against the cap is already under Risk / sh.
  const checks = plan.checks.filter(c => c.id !== 'risk');
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
