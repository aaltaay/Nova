/** Nova Marketing Sample Data: a Setups board for the sample desk (`?view=sample`).
 * Shapes match `/ws/setups`; nothing here reaches the backend. */
import type { ScoreStats, Scoreboard, SetupsBoard } from '../setups/types';

const T = 1_790_000_000;

export const SAMPLE_SETUPS_BOARD: SetupsBoard = {
  schema_version: 1,
  generated_at: T,
  session_date: '2026-09-22',
  universe: 24,
  seeding: 0,
  scoreboard: true,
  scoreboard_error: null,
  proposing: true,
  proposals: [],
  rows: [
    {
      symbol: 'NVXA', state: 'near', reason: '0.02 under the 4.37 trigger -- read the tape', kind: 'first_pullback',
      nth: 0, setup_id: 'NVXA-2026-09-22-1', last_price: 4.35, distance: 0.02, grade: 'A',
      setup: { trigger: 4.37, entry: 4.38, stop: 4.30, risk: 0.08, target1: 4.54, pullback_bars: 1,
               leg_high: 4.39, leg_low: 3.99, leg_pct: 0.1003, kind: 'first_pullback' },
      leg: { t: T - 180, high: 4.39, low: 3.99, pct: 0.1003 },
      pillars: { price: 4.35, change_pct: 38.2, rvol: 12.4, float: 6_100_000, news: true, headline: 'Sample headline' },
      tape: { verdict: 'go', reasons: ['green on the tape (5 prints, 2.4k at the ask)', 'seller at 4.40 thinning out (30k to 9k)'],
              line: { depth: true, tape: true } },
      proposal: { id: 'sample-1', setup_id: 'NVXA-2026-09-22-1', symbol: 'NVXA', kind: 'first_pullback', trigger: 4.37,
                  entry: 4.38, stop: 4.30, target1: 4.54, risk: 0.08, grade: 'A',
                  reasons: ['green on the tape (5 prints, 2.4k at the ask)'], created_at: T, status: 'open', tape_now: 'go' },
      outcome: null, bar_r: null, mfe: null, mae: null,
    },
    {
      symbol: 'QMBL', state: 'armed', reason: 'trigger 7.12, stop 6.98, risk 0.15', kind: 'first_pullback', nth: 0,
      setup_id: 'QMBL-2026-09-22-1', last_price: 7.02, distance: 0.10, grade: 'B',
      setup: { trigger: 7.12, entry: 7.13, stop: 6.98, risk: 0.15, target1: 7.43, pullback_bars: 2,
               leg_high: 7.20, leg_low: 6.61, leg_pct: 0.0893, kind: 'first_pullback' },
      leg: { t: T - 300, high: 7.20, low: 6.61, pct: 0.0893 },
      pillars: { price: 7.02, change_pct: 22.0, rvol: 7.1, float: 14_000_000, news: false, headline: null },
      tape: { verdict: 'blind', reasons: ['no fresh Level 2 -- open its Level 2 so the bot can read the tape'],
              line: { depth: false, tape: false } },
      proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
    },
    {
      symbol: 'HLTR', state: 'triggered', reason: 'traded 3.05 over the 3.04 trigger', kind: 'first_pullback', nth: 1,
      setup_id: 'HLTR-2026-09-22-1', last_price: 3.21, distance: null, grade: 'A',
      setup: { trigger: 3.04, entry: 3.05, stop: 2.97, risk: 0.08, target1: 3.21, pullback_bars: 1,
               leg_high: 3.10, leg_low: 2.80, leg_pct: 0.1071, kind: 'first_pullback', triggered_at: T - 420 },
      leg: { t: T - 600, high: 3.10, low: 2.80, pct: 0.1071 },
      pillars: { price: 3.05, change_pct: 55.1, rvol: 21.0, float: 3_200_000, news: true, headline: 'Sample headline' },
      tape: null, proposal: null, outcome: 'target_first', bar_r: 1.44, mfe: 0.19, mae: -0.02,
    },
    {
      symbol: 'ORBT', state: 'leg', reason: 'new high 12.40 on a 7.2% leg -- wait for the pullback', kind: 'first_pullback',
      nth: 0, setup_id: null, last_price: 12.38, distance: null, grade: null, setup: null,
      leg: { t: T - 60, high: 12.40, low: 11.57, pct: 0.0717 },
      pillars: null, tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
    },
  ],
};

const stat = (armed: number, triggered: number, tf: number, sf: number, win: number | null,
              r: number | null, net: number | null): ScoreStats => ({
  armed, triggered, trigger_rate: armed ? Math.round((triggered / armed) * 1000) / 1000 : null,
  target_first: tf, stop_first: sf, open: triggered - tf - sf, scored: triggered,
  win_pct: win, avg_r: r, avg_net_r: net, avg_mfe_r: null, avg_mae_r: null,
});

/** Nova Marketing Sample Data: the scoreboard's shape with illustrative counts. */
export const SAMPLE_SETUPS_SCOREBOARD: Scoreboard = {
  days: 5,
  date_from: '2026-09-18',
  row_count: 14,
  summary: {
    all: stat(14, 9, 4, 4, 44.4, 0.12, -0.05),
    by: {
      tape_at_trigger: {
        go: stat(5, 5, 3, 1, 60.0, 0.41, 0.22),
        wait: stat(3, 2, 0, 2, 0.0, -0.71, -0.93),
        blind: stat(6, 2, 1, 1, 50.0, 0.20, 0.02),
      },
      grade: { A: stat(6, 4, 2, 1, 50.0, 0.30, 0.11), B: stat(8, 5, 2, 3, 40.0, -0.02, -0.19) },
      session: { premarket: stat(5, 3, 1, 2, 33.3, -0.10, -0.31), regular: stat(9, 6, 3, 2, 50.0, 0.23, 0.05) },
      kind: { first_pullback: stat(10, 7, 4, 2, 57.1, 0.33, 0.14), second_pullback: stat(4, 2, 0, 2, 0.0, -0.61, -0.80) },
    },
  },
};
