/**
 * HOD Momo strip -- the compact alert strip across the top of the Scanner
 * board (approved UX redesign, 2026-09-21). Feature-local constants
 * (AGENTS.md section 6.1): labels, tunables and the persisted-state contract.
 *
 * Persisted state (persisted-state.mdc):
 *   owner        hod_momo/hodMomoStripPersist.ts
 *   key          HOD_MOMO_STRIP_STORAGE_KEY (localStorage)
 *   invalidation schema bump -- an unknown schema_version is refused loud
 *                (console.warn) and the defaults are used; nothing is migrated
 *                from the retired `nova.hodMomo.dock.v2.*` keys on purpose,
 *                their heights were table pixels, not strip rows.
 */

export const HOD_MOMO_STRIP_STORAGE_KEY = 'nova.hodMomo.strip.v1';
export const HOD_MOMO_STRIP_SCHEMA_VERSION = 1;

/** One alert row: one line, no wrapping. */
export const HOD_MOMO_STRIP_ROW_PX = 22;
/** The strip can always show one row. */
export const HOD_MOMO_STRIP_MIN_ROWS = 1;
/** Hard ceiling on rows regardless of viewport (the live max is 40% of the content column). */
export const HOD_MOMO_STRIP_MAX_ROWS = 40;
/** Share of the content column's height the strip body may take when dragged. */
export const HOD_MOMO_STRIP_MAX_SHARE = 0.4;
export const HOD_MOMO_STRIP_DEFAULT_ROWS = 4;
export const HOD_MOMO_STRIP_DEFAULT_FOLDED = false;
/** Fallback content-column height when nothing is measurable (tests, first paint). */
export const HOD_MOMO_STRIP_FALLBACK_CONTENT_PX = 900;

/** An alert first seen by this strip counts as NEW for this long. */
export const HOD_MOMO_STRIP_NEW_MS = 60_000;
/** Arrival highlight (CSS animation) length. */
export const HOD_MOMO_STRIP_FLASH_MS = 2_600;

export const HOD_MOMO_STRIP_TITLE = 'HOD Momo';
export const HOD_MOMO_STRIP_NEW_FLAG = 'NEW';
export const HOD_MOMO_STRIP_FOLD_TITLE = 'Fold the strip to its header';
export const HOD_MOMO_STRIP_UNFOLD_TITLE = 'Unfold the strip';
export const HOD_MOMO_STRIP_GRIP_TITLE = 'Drag to resize (snaps to whole rows)';
export const HOD_MOMO_STRIP_GRIP_LABEL = 'Resize HOD Momo strip';
export const HOD_MOMO_STRIP_MORE_TITLE = 'Sound, strategies, clear, configure';
export const HOD_MOMO_STRIP_ROW_TITLE = 'Click to select in the side panel · ticker opens Trader';
export const HOD_MOMO_STRIP_EMPTY_WAITING = 'No alerts yet';
export const HOD_MOMO_STRIP_EMPTY_CONNECTING = 'Connecting to the HOD Momo feed';
export const HOD_MOMO_STRIP_FEED_LIVE = 'feed live';
export const HOD_MOMO_STRIP_FEED_OFFLINE = 'feed offline';
export const HOD_MOMO_STRIP_NO_GATE_VALUES = 'no gate values on this alert';

export const HOD_MOMO_STRIP_MENU_SOUND = 'Alert sound';
export const HOD_MOMO_STRIP_MENU_STRATEGIES = 'Strategies';
export const HOD_MOMO_STRIP_MENU_CLEAR = "Clear today's alerts";
export const HOD_MOMO_STRIP_MENU_CONFIGURE = 'Configure strategies';
export const HOD_MOMO_STRIP_MENU_DEBUG_ON = 'Show debug panel';
export const HOD_MOMO_STRIP_MENU_DEBUG_OFF = 'Hide debug panel';

/** Integrity dot words (from /api/integrity via useHodMomoIntegrity). */
export const HOD_MOMO_STRIP_INTEGRITY_LABEL: Record<string, string> = {
  pass: 'integrity ok',
  warn: 'integrity warn',
  fail: 'integrity fail',
  error: 'integrity unreachable',
  loading: 'integrity …',
};

/** Gate value keys shown after the strategy chip, in this order, exactly as
 * the alert carries them (hod_momo/types.ts). Nothing is derived. */
export const HOD_MOMO_STRIP_GATE_KEYS = [
  'change_pct',
  'rvol',
  'rvol_5min',
  'float_shares',
  'gap_pct',
  'volume',
  'momentum_pct',
] as const;

export const HOD_MOMO_STRIP_GATE_LABEL: Record<(typeof HOD_MOMO_STRIP_GATE_KEYS)[number], string> = {
  change_pct: 'chg',
  rvol: 'rvol',
  rvol_5min: 'rvol5m',
  float_shares: 'float',
  gap_pct: 'gap',
  volume: 'vol',
  momentum_pct: 'momo',
};

export function hodMomoStripSinceLabel(count: number, since: string | null): string {
  const alerts = `${count} alert${count === 1 ? '' : 's'}`;
  return since ? `${alerts} since ${since}` : alerts;
}

export function hodMomoStripStrategyChip(strategyId: number): string {
  return `S${strategyId}`;
}

// ── QA batch: Scanner / HOD / desk honesty (2026-09-22) ────────────────────
/** A trigger print this much older than its alert is named in the row title (QA V16). */
export const HOD_MOMO_STRIP_PRINT_LAG_NOTE_SEC = 60;

// ── One row per ticker per batch (operator ask, 2026-09-23) ────────────────
/**
 * Strategies that fire for one ticker together share a row with a count
 * bubble. "Together" is the backend's consolidation batch: a symbol's alerts
 * wait `master.consolidation_sec` and leave at once, one per strategy, each
 * stamped with its own newest fire, so one batch spans up to that window plus
 * the flush loop's tick. Fallback mirrors backend
 * constants_hod_momo.HOD_MOMO_CONSOLIDATION_SEC for when config is not loaded.
 */
export const HOD_MOMO_STRIP_GROUP_FALLBACK_SEC = 10;
/** backend hod_momo_alerts.flush_consolidated_loop sleeps 1 s between flushes. */
export const HOD_MOMO_STRIP_GROUP_SLACK_SEC = 1;
/** Hover card: gap below the bubble, and the least distance kept from the viewport edge. */
export const HOD_MOMO_STRIP_CARD_GAP_PX = 4;
export const HOD_MOMO_STRIP_CARD_MARGIN_PX = 8;

export function hodMomoStripGroupWindowSec(consolidationSec: number | null | undefined): number {
  const base = typeof consolidationSec === 'number' && Number.isFinite(consolidationSec) && consolidationSec > 0
    ? consolidationSec
    : HOD_MOMO_STRIP_GROUP_FALLBACK_SEC;
  return base + HOD_MOMO_STRIP_GROUP_SLACK_SEC;
}

export function hodMomoStripGroupTitle(ticker: string, count: number, clock: string): string {
  return `${ticker} · ${count} strategies at ${clock}`;
}

export function hodMomoStripBubbleLabel(count: number, names: readonly string[]): string {
  return `${count} strategies fired together: ${names.join(', ')}`;
}
