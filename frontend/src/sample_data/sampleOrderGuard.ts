/**
 * One predicate the IBKR transport modules ask before any order mutation (#357).
 *
 * Scope, stated exactly: the refusals here give the order doors under
 * src/ibkr/ -- placeIbkrOrder, cancelIbkrOrder, cancelAllOrdersForSymbol,
 * cancelAllWorkingOrders, flattenAccount -- plus the runEmergencyKill
 * composite their own copy, and `onSampleDesk` is what the other live-desk
 * controls ask (venue pills, bot writes, desk arming, depth / tape lines).
 * The guarantee that nothing at all leaves the sample desk is the transport
 * gate underneath every caller (sampleNetworkGate, V4): a door missing from
 * this list still sends nothing, it only loses the friendly copy.
 *
 * Direction matters: a false positive would silently block real order
 * placement, so this refuses only on an exact `view=sample` match and returns
 * null everywhere else, including when there is no browser at all
 * (sampleNav.isSampleView answers false off-browser).
 */
import { isSampleView } from './sampleNav';
import { SAMPLE_KILL_REFUSAL, SAMPLE_ORDER_REFUSAL } from './sampleCopy';

/** True only on the ?view=sample route, in a browser. */
export function onSampleDesk(): boolean {
  return isSampleView();
}

export function sampleOrderRefusal(): string | null {
  return onSampleDesk() ? SAMPLE_ORDER_REFUSAL : null;
}

/** Emergency KILL refuses as one unit, with its own actionable copy. */
export function sampleKillRefusal(): string | null {
  return onSampleDesk() ? SAMPLE_KILL_REFUSAL : null;
}
