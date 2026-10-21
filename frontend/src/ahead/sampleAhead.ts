/**
 * Ahead on the demo desk (ADR 043, ADR 061): Nova Marketing Sample Data answers that there is no forecaster, so the
 * demo shows only Nova's own lines carried on to where they meet. It never draws a forecast built on sample data.
 */
import { AHEAD_HORIZON, AHEAD_NEVER, AHEAD_STEP_SEC, AHEAD_WORDS } from './aheadConstants';
import type { AheadAnswer, AheadStatus } from './aheadTypes';

export function sampleAhead(symbol: string, nowS: number): AheadAnswer {
  return {
    schema_version: 1,
    symbol: symbol.toUpperCase(),
    generated_at: nowS,
    replay: false,
    venue: 'paper',
    bar_t: null,
    as_of: null,
    bars: { n: 0, contiguous_tail: 0, tail_gap_sec: null },
    price: null,
    prior_close: null,
    volume_last15: null,
    ai: {
      state: 'not_set_up',
      reason: AHEAD_WORDS.demoReason,
      need: null,
      have: null,
      retry_ms: null,
      retry_at: null,
      model: null,
      exam_passed: null,
      exam: null,
      horizon_min: AHEAD_HORIZON,
      step_sec: AHEAD_STEP_SEC,
      levels: null,
      close: null,
      volume: null,
      paths: null,
      volume_15: null,
      range_15: null,
      compute_ms: null,
      issued_at: null,
    },
    never: AHEAD_NEVER,
  };
}

export function sampleAheadStatus(nowS: number = Date.now() / 1000): AheadStatus {
  return { schema_version: 1, configured: false, reason: AHEAD_WORDS.demoStatus, checked_at: nowS, health: null };
}
