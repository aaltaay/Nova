/**
 * The Scanner's home tab, in a module with no runtime imports (#639). The nav-rail store reads it
 * while it loads, and the registry reaches that store through a cycle (registry -> modules ->
 * QuoteHeaderPanel -> the workspace barrel -> navRailStore), so the value cannot live in the
 * registry: a page that loads the registry first would find it not yet defined.
 */
import type { ActiveTab } from './registry';

/** Scanner homepage — Gappers (Dashboard config tab removed; Settings owns config). */
export const DEFAULT_ACTIVE_TAB: ActiveTab = 'gappers';
