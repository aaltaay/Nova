/**
 * Which setups climbed their ladder between two live frames of the setup
 * scanner's board (`/ws/setups`, ADR 022 / 031) -- what the watch list's toasts
 * announce for a watched symbol (operator ask, 2026-09-24: "shouldn't these
 * toast notifications be watching if a strategy is forming?"). Pure: a board
 * and the memory of the frames before it in, the climbs and the next memory out.
 *
 * The ladder: forming (`leg` or `pullback`) -> `armed` -> `near` -> `triggered`.
 * `failed`, `filtered`, `watching` and a setup off the board are off it. A
 * climb is announced once per setup (its `setup.leg_t`), and forming at most
 * once per WATCH_SETUP_FORMING_REPEAT_MS per symbol and setup, so a price
 * wobbling in and out of the near band, or a setup held back and freed again,
 * is one toast. A triggered setup, or an armed or near one a newer leg
 * replaced, ends its ladder: what forms next counts from the bottom again.
 *
 * The first frame a memory reads -- a page load, a reconnect, a return from
 * Sim, a new session -- only sets the baseline: nothing already on the board is
 * announced as new. Every symbol is remembered, watched or not, so watching a
 * symbol mid-setup announces only what comes next.
 */
import { setupTypeOf, type SetupRow, type SetupsBoard } from '../setups';
import { WATCH_SETUP_FORMING_REPEAT_MS } from './watchListConstants';
import type { WatchSetupStage } from './types';

export type { WatchSetupStage } from './types';

const STAGES: readonly WatchSetupStage[] = ['forming', 'armed', 'near', 'triggered'];
/** The rung each board state stands on; any other state is off the ladder (0). */
const RUNG: Readonly<Record<string, number>> = { leg: 1, pullback: 1, armed: 2, near: 3, triggered: 4 };
const ARMED = 2;

/** One setup's climb, as the toast folds it in. */
export interface WatchSetupClimb {
  symbol: string;
  setupType: string;
  stage: WatchSetupStage;
  row: SetupRow;
  /** Epoch seconds of the frame that showed the climb. */
  at: number;
}

interface Seen {
  rung: number;
  /** The leg the setup stands on: the armed setup's, else the forming leg's. */
  leg: number | null;
}

export interface SetupClimbMemory {
  session: string | null;
  /** `SYMBOL|setup` -> where the last frame had it. */
  seen: ReadonlyMap<string, Seen>;
  /** `SYMBOL|setup|rung|leg` -> when it was announced (ms). */
  told: ReadonlyMap<string, number>;
}

export function rungOf(state: string): number {
  return RUNG[state] ?? 0;
}

function legOf(row: SetupRow): number | null {
  const t = row.setup?.leg_t ?? row.leg?.t;
  return typeof t === 'number' && Number.isFinite(t) ? t : null;
}

/** Pure: the climbs `board` shows over `memory` (null: nothing read yet), and the memory after it. */
export function setupClimbs(
  memory: SetupClimbMemory | null,
  board: SetupsBoard,
  nowMs: number,
): { climbs: WatchSetupClimb[]; memory: SetupClimbMemory } {
  const prior = memory && memory.session === board.session_date ? memory : null;
  const seen = new Map<string, Seen>();
  const told = new Map<string, number>(prior ? prior.told : []);
  const climbs: WatchSetupClimb[] = [];
  for (const row of board.rows ?? []) {
    const symbol = String(row.symbol ?? '').trim().toUpperCase();
    const setupType = setupTypeOf(row);
    const key = `${symbol}|${setupType}`;
    if (!symbol || seen.has(key)) continue;
    const rung = rungOf(row.state);
    const leg = legOf(row);
    seen.set(key, { rung, leg });
    if (!prior || rung === 0) continue;
    const before = prior.seen.get(key);
    let was = before?.rung ?? 0;
    // A setup on a new leg where an armed / near / triggered one stood is a new setup.
    if (was >= ARMED && rung <= was && leg !== before?.leg) was = 0;
    if (rung <= was) continue;
    // Armed and above: once per setup. Forming (or a setup with no leg): once per cool-down.
    const once = rung >= ARMED && leg !== null;
    const toldKey = `${key}|${rung}|${once ? leg : ''}`;
    const last = told.get(toldKey);
    if (last !== undefined && (once || nowMs - last < WATCH_SETUP_FORMING_REPEAT_MS)) continue;
    told.set(toldKey, nowMs);
    climbs.push({ symbol, setupType, stage: STAGES[rung - 1], row, at: board.generated_at });
  }
  return { climbs, memory: { session: board.session_date, seen, told } };
}
