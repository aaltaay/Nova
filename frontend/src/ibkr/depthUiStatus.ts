/**
 * Pure status strings for DepthLadder — kept out of the React component so
 * reconnect / cap / empty-state regressions are unit-testable without a DOM.
 */
import { BOT_SETUP_LABELS } from '../constantGroups/bot';
import {
  L2_LENT_BACK,
  L2_LENT_PREFIX,
  L2_LENT_SOMEONE,
  L2_LENT_WHY_WORDS,
} from '../constantGroups/market_ui';

/** The line went to a setup (ADR 043): who took it, and why -- what the lent frame and the poll say. */
export interface DepthLentTo {
  symbol: string | null;
  setupType: string | null;
  /** trade | near | armed (the loan's reason now). */
  tier: string | null;
  /** The backend's words for the reason, when it sends no tier the desk knows. */
  why: string | null;
}

/**
 * "Level 2 lent to AISP's first pullback (near its trigger) — back when it ends or when you
 * bring this tab to the front". Built from the desk's own words; a frame that names no
 * borrower says one of Nova's setups took it.
 */
export function depthLentText(to: DepthLentTo): string {
  const label = to.setupType ? (BOT_SETUP_LABELS[to.setupType] ?? to.setupType.replace(/_/g, ' ')) : null;
  const who = to.symbol ? `${to.symbol}'s ${(label ?? 'setup').toLowerCase()}` : L2_LENT_SOMEONE;
  const why = (to.tier ? L2_LENT_WHY_WORDS[to.tier] : null) ?? to.why;
  return `${L2_LENT_PREFIX} ${who}${to.symbol && why ? ` (${why})` : ''} — ${L2_LENT_BACK}`;
}

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
