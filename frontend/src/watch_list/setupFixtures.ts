/** Test rows and boards in the `/ws/setups` shape for the watch list's setup toasts and Setup column. */
import type { SetupRow, SetupsBoard, SetupState } from '../setups';

export const FIXTURE_LEG_A = 1_790_000_000;
export const FIXTURE_LEG_B = FIXTURE_LEG_A + 600;

/** A first-pullback row in `state` on the leg that started at `leg`; armed and later carry levels. */
export function setupRow(symbol: string, state: SetupState, patch: Partial<SetupRow> = {}, leg = FIXTURE_LEG_A): SetupRow {
  const armed = state === 'armed' || state === 'near' || state === 'triggered' || state === 'filtered';
  return {
    symbol,
    setup_type: 'first_pullback',
    state,
    reason: `${state} reason`,
    kind: 'first_pullback',
    nth: 0,
    setup_id: armed ? `${symbol}-${leg}` : null,
    setup: armed
      ? { leg_t: leg, trigger: 4.37, entry: 4.38, stop: 4.3, risk: 0.08, target1: 4.54, pullback_bars: 1,
        leg_high: 4.39, leg_low: 3.99, leg_pct: 0.1 }
      : null,
    leg: { t: leg, high: 4.39, low: 3.99, pct: 0.1 },
    last_price: 4.35,
    distance: state === 'near' ? 0.02 : null,
    grade: null,
    pillars: null,
    tape: null,
    proposal: null,
    outcome: null,
    bar_r: null,
    mfe: null,
    mae: null,
    ...patch,
  };
}

/** A live board holding `rows`. */
export function setupBoard(rows: SetupRow[], patch: Partial<SetupsBoard> = {}): SetupsBoard {
  return {
    schema_version: 2,
    generated_at: FIXTURE_LEG_A + 900,
    session_date: '2026-09-24',
    source: 'live',
    universe: 3,
    universe_symbols: ['GRML', 'ONCO', 'PFSA'],
    seeding: 0,
    scoreboard: true,
    scoreboard_error: null,
    proposing: false,
    rows,
    proposals: [],
    ...patch,
  };
}
