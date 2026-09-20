/**
 * One predicate the IBKR transport modules ask before any order mutation (#357).
 *
 * Direction matters: a false positive here would silently block real order
 * placement, so this returns null unless the URL is exactly the sample route.
 * The `window` check is load-bearing -- vitest declares no default environment
 * (vite.config.ts), so src/ibkr/*.test.ts run in node where reading
 * window.location would throw.
 */
import { isSampleView } from './sampleNav';
import { SAMPLE_ORDER_REFUSAL } from './sampleCopy';

export function sampleOrderRefusal(): string | null {
  if (typeof window === 'undefined') return null;
  return isSampleView() ? SAMPLE_ORDER_REFUSAL : null;
}
