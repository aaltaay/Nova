/** Ahead (ADR 061): the wire from `/api/ahead/*` and the shapes the desk works out itself.
 *
 * Schema: architecture/schema/ahead.md. The backend (`backend/ahead/view.py`) answers `AheadAnswer` and
 * `AheadStatus`; everything below "Worked out on the desk" is computed here from that answer, the stock read the
 * page already holds (Nova's trend lines, level zones and setup lanes) and the chart's own candles. A forecast is
 * never data: every number from `ai` is the forecaster's view and is drawn and labelled as such.
 */

// ---------------------------------------------------------------- the wire

export type AheadAiState =
  | 'ready'
  | 'pending'
  | 'not_set_up'
  | 'offline'
  | 'warming'
  | 'not_enough_bars'
  | 'quiet'
  | 'error';

export interface AheadScore {
  spearman: number;
  miss_x: number;
}

/** The forecaster's own exam, as its health reports it (null until one has run). */
export interface AheadExam {
  passed: boolean;
  as_of: string;
  /** One plain sentence a trader can read. */
  summary: string;
  /** What kind of stocks and hours the exam covered; null from a forecaster that does not say. */
  scope: string | null;
  volume: { model: AheadScore; baseline: AheadScore & { name: string } };
  range: { model: AheadScore; baseline: AheadScore & { name: string } };
  /** Share of outcomes inside the forecaster's 80% range (0-1). */
  band80_coverage: number;
  sample: { days: number; moments: number };
}

export interface AheadModel {
  name: string;
  version: string;
}

export interface AheadPaths {
  n: number;
  /** `n` rows of `horizon_min` closes. */
  close: number[][];
  /** How the per-minute ranges were joined into paths (the desk says so wherever it uses them). */
  joined_by: string;
}

/** The forecaster's view. Every field marked "ready only" is null unless `state === 'ready'`. */
export interface AheadAi {
  state: AheadAiState;
  /** Plain words whenever `state !== 'ready'`. */
  reason: string | null;
  /** not_enough_bars: candles needed and candles held. */
  need: number | null;
  have: number | null;
  /** pending: ask again after this many ms. */
  retry_ms: number | null;
  /** offline after repeated misses: when Nova asks again (epoch seconds). */
  retry_at: number | null;
  model: AheadModel | null;
  /** From the forecast answer; null when not ready. */
  exam_passed: boolean | null;
  /** From the forecaster's health; null when no exam has run or the health is unknown. */
  exam: AheadExam | null;
  horizon_min: number;
  step_sec: number;
  // --- ready only ---
  /** Quantile levels, always exactly [0.1, 0.25, 0.5, 0.75, 0.9]. */
  levels: number[] | null;
  /** `horizon_min` rows, one column per level, each row ascending. */
  close: number[][] | null;
  volume: number[][] | null;
  paths: AheadPaths | null;
  /** Next 15 minutes' total volume and (high - low) / last close, one value per level. */
  volume_15: number[] | null;
  range_15: number[] | null;
  compute_ms: number | null;
  /** When Nova received it (epoch seconds). */
  issued_at: number | null;
}

/** `GET /api/ahead/forecast/{symbol}`: 200 for every state, 422 only for a bad symbol. */
export interface AheadAnswer {
  schema_version: 1;
  symbol: string;
  /** The desk clock when answered (the playhead on a replay), epoch seconds. Always >= `as_of`. */
  generated_at: number;
  replay: boolean;
  venue: 'live' | 'paper' | 'sim';
  /** Start of the newest completed 1-minute candle sent; null with no candles. */
  bar_t: number | null;
  /** `bar_t + 60`: the forecast starts here. Null only with no candles. */
  as_of: number | null;
  bars: {
    n: number;
    /** How many of the newest candles are consecutive minutes. */
    contiguous_tail: number;
    /** Desk minute minus `as_of`, seconds; null with no candles. */
    tail_gap_sec: number | null;
  };
  /** Newest completed close (real). */
  price: number | null;
  prior_close: number | null;
  /** Real volume of the candles that closed in the last 15 minutes. */
  volume_last15: number | null;
  ai: AheadAi;
  /** "A forecast only: nothing here places, blocks, sizes or delays an order." */
  never: string;
}

export interface AheadLiveScore {
  since: string | null;
  scored: number;
  volume_spearman: number | null;
  range_spearman: number | null;
  band80_coverage: number | null;
}

/** `GET /api/ahead/status`: is a forecaster set up, and what its health says. */
export interface AheadStatus {
  schema_version: 1;
  configured: boolean;
  /** Plain words when not configured or not reachable. */
  reason: string | null;
  checked_at: number;
  health: {
    state: 'ready' | 'warming' | 'error';
    detail: string | null;
    contract_ok: boolean;
    model: AheadModel | null;
    exam: AheadExam | null;
    live: AheadLiveScore;
  } | null;
}

// ---------------------------------------------------------------- worked out on the desk

export type AheadScope = 'all' | 'lines' | 'flat_top' | 'first_pullback';

export interface AheadPrefs {
  /** The toolbar switch; off by default. While off the desk asks nothing. */
  shown: boolean;
  scope: AheadScope;
  /** "Show before it has earned it": off by default. */
  unearned: boolean;
}

/** Nova's own 1-minute support and resistance carried on from the newest candle (no AI). */
export interface AheadLines {
  state: 'meet' | 'none' | 'past';
  /** Words whenever `state !== 'meet'`. */
  reason: string | null;
  supportId: string | null;
  resistanceId: string | null;
  /** Both lines' prices at the newest completed candle (re-anchored there). */
  supportP: number | null;
  resistanceP: number | null;
  /** Price per candle. */
  supportSlope: number | null;
  resistanceSlope: number | null;
  meet: {
    /** Candles after the newest one (fractional). */
    inCandles: number;
    /** Epoch seconds, or null when the stock skips minutes (then it is counted in candles). */
    t: number | null;
    p: number;
    withinZone: boolean;
  } | null;
}

export interface AheadWall {
  zoneId: string;
  price: number;
  label: string;
}

/** Which wall first: shares of paths whose minute close reaches each wall first within the horizon. */
export interface AheadWalls {
  above: AheadWall | null;
  below: AheadWall | null;
  /** Null unless the AI view is shown. */
  first: { above: number | null; below: number | null; neither: number } | null;
  nPaths: number | null;
  /** `as_of + horizon` (epoch seconds). */
  byT: number | null;
  reason: string | null;
}

export type AheadLaneState = 'armed' | 'near' | 'forming' | 'triggered';
export type AheadPathOutcome = 'target' | 'stop' | 'open' | 'no';

/** "If it triggers": of the paths that reach the setup's trigger, which comes first, target or stop. */
export interface AheadTrigger {
  family: 'flat_top' | 'first_pullback';
  setupType: string | null;
  state: AheadLaneState | null;
  /** True for a forming setup (its levels may still move). */
  provisional: boolean;
  trigger: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  /** Share of paths that reach the trigger; null unless the AI view is shown. */
  reach: number | null;
  nReach: number | null;
  first: { target: number; stop: number; open: number } | null;
  /** Outcome of each drawn path (the first 16), for colouring. */
  perPath: AheadPathOutcome[] | null;
  reason: string | null;
}
