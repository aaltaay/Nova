/**
 * Pure status strings for DepthLadder — kept out of the React component so
 * reconnect / cap / empty-state regressions are unit-testable without a DOM.
 */

export function depthEmptyMessage(
  symbol: string,
  connected: boolean,
  error: string | null,
): string {
  if (error) return error;
  if (connected) return 'Waiting for book data…';
  return `Connecting depth for ${symbol}…`;
}

export type DepthLiveBadge =
  | { kind: 'error'; text: string }
  | { kind: 'reconnecting' }
  | { kind: 'l1' }
  | null;

/**
 * When a prior book is on screen, prefer the backend error text over a
 * forever "Reconnecting…" badge (Symbol cap reached used to hide behind that).
 */
export function depthLiveBadge(
  connected: boolean,
  error: string | null,
  l1Fallback: boolean,
): DepthLiveBadge {
  if (error) return { kind: 'error', text: error };
  if (!connected) return { kind: 'reconnecting' };
  if (l1Fallback) return { kind: 'l1' };
  return null;
}

export function depthLiveBadgeText(badge: DepthLiveBadge): string | null {
  if (badge == null) return null;
  if (badge.kind === 'error') return badge.text;
  if (badge.kind === 'reconnecting') return 'Reconnecting depth…';
  return 'Level 1 only — depth entitlement pending';
}
