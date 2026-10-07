/**
 * A short plan's short checks (ADR 048, #778 step 3), in its check list: the one short check the execution door
 * runs -- borrow, SSR, the halt, the hours, the margin cushion with its liquidation price, the buy stop, "you
 * hold none long" and equity -- asked read-only for the plan's size, entry, stop and cover. It describes; the
 * door decides when a short is sent. The sample desk asks nothing.
 */
import { useShortCheck, type ShortCheckRule } from '../ibkr';
import { tipProps } from '../ux';
import { STATE_WORDS, STOCK_READ_SHORT_CHECK_POLL_MS } from './constants';
import { checkGlyph } from './planMath';
import type { StockPlan } from './types';

function line(rule: ShortCheckRule): string {
  return rule.value ? `${rule.label} · ${rule.value}` : rule.label;
}

export function ShortPlanChecks({ symbol, plan, size }: { symbol: string; plan: StockPlan; size: number | null }) {
  const asks = plan.side === 'short' && plan.entry !== null;
  const state = useShortCheck(symbol, asks
    ? { qty: size ?? 1, price: plan.entry, stop: plan.stop, target: plan.target }
    : null, STOCK_READ_SHORT_CHECK_POLL_MS);
  if (!asks) return null;
  const { check, unavailable, error } = state;
  if (unavailable) return null;
  if (!check) {
    return error ? (
      <p className="sr-plan__risk-note" data-testid="stock-read-short-checks-error">
        The short check could not be read ({error}): the door still checks every short when it is sent.
      </p>
    ) : null;
  }
  return (
    <ul className="sr-checks sr-checks--short" data-testid="stock-read-short-checks" aria-label="Short check">
      {check.rules.map(rule => (
        <li key={`${rule.id}:${rule.label}`} className={`sr-check sr-check--${rule.state}`}
          {...tipProps(rule.text || line(rule), `Short check · ${STATE_WORDS[rule.state]}`)}
          data-testid={`stock-read-short-check-${rule.id}`}>
          <span className="sr-check__glyph" aria-label={STATE_WORDS[rule.state]}>{checkGlyph(rule.state)}</span>
          {line(rule)}
        </li>
      ))}
    </ul>
  );
}
