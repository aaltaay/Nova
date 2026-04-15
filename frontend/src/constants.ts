/**
 * Authoritative UI policy and thresholds for B.L.A.S.T.
 * Keep numeric rules in sync with `backend/constants.py` where they overlap.
 */

// ── Market cap tiers (USD) ─────────────────────────────────────────────────
export const SMALL_CAP_MIN =   300_000_000;   //  $300 M
export const SMALL_CAP_MAX = 2_000_000_000;   //   $2 B
export const MID_CAP_MIN   = 2_000_000_000;   //   $2 B
export const MID_CAP_MAX   = 10_000_000_000;  //  $10 B
export const LARGE_CAP_MIN = 10_000_000_000;  //  $10 B

// ── News flame thresholds (hours) ──────────────────────────────────────────
export const NEWS_FLAME_HOT_HOURS  =  2;   // red badge    (0 –  2 h)
export const NEWS_FLAME_WARM_HOURS = 12;   // orange badge (2 – 12 h)
export const NEWS_FLAME_MAX_HOURS  = 24;   // yellow badge (12 – 24 h); hide above this

// ── Relative volume ────────────────────────────────────────────────────────
export const REL_VOLUME_HIGH = 2;   // highlight threshold (≥ 2×)

// ── Minimum price filter (mirror backend SCANNER_MIN_PRICE) ─────────────────
export const SCANNER_MIN_PRICE = 0.50;  // exclude any stock priced below $0.50 (gainers + gappers)

// ── Gapper filter (mirror backend GAPPER_MIN_GAP_PCT) ───────────────────────
export const GAPPER_MIN_GAP_PCT = 10;   // minimum gap % vs prior close to show as a gapper

// ── News Catalysts tab ────────────────────────────────────────────────────────
// Label shown on the experimental Catalysts tab badge
export const CATALYSTS_EXPERIMENTAL_LABEL = 'Experimental';
