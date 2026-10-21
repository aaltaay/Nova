/**
 * Odds Nova works out from the forecaster's paths (ADR 065). Pure. The paths are the forecaster's minute ranges
 * joined into whole paths by an assumed path shape (`ai.paths.joined_by`), and every count here reads minute CLOSES
 * only (a wick that touches is not seen), so the odds carry both assumptions and the desk says so beside them.
 *
 * - Which wall first: per path, the first minute close at or over the wall above, or at or under the wall below.
 * - If it triggers: per path, the fill minute is the first close over the setup's trigger (the order fills at the
 *   trigger); from that minute on (the fill minute included) the first close at or over target 1 or at or under the
 *   stop decides; neither by the zone's end is "open". Raw path closes, the same basis as the wall odds.
 */
import {
  AHEAD_DRAWN_PATHS,
  AHEAD_FAMILY_WORD,
  AHEAD_FORMING_STATES,
  AHEAD_HORIZON,
  AHEAD_LANE_RANK,
  AHEAD_SETUP_FAMILIES,
  AHEAD_STEP_SEC,
  AHEAD_WORDS,
  type AheadFamily,
} from './aheadConstants';
import { etHhmm, nearestWalls, type AheadZoneIn } from './aheadGeometry';
import type { AheadLaneState, AheadPathOutcome, AheadTrigger, AheadWalls } from './aheadTypes';

interface LevelsIn {
  trigger: number;
  entry: number;
  stop: number;
  target1: number;
}

/** The fields of a stock-read setup lane Ahead reads. */
export interface AheadLaneIn {
  setup_type: string;
  state: string;
  side?: 'long' | 'short';
  timeframe?: '1m' | '5m';
  setup: (LevelsIn & { triggered_at?: number }) | null;
  forming: LevelsIn | null;
}

/** The fields of the stock read Ahead's strategy scopes read. */
export interface AheadReadIn {
  followed: boolean;
  followed_note: string | null;
  setups: readonly AheadLaneIn[];
}

// ---------------------------------------------------------------- which wall first

export function wallFirst(
  paths: readonly (readonly number[])[], above: number | null, below: number | null,
): { above: number | null; below: number | null; neither: number } | null {
  const n = paths.length;
  if (n === 0 || (above === null && below === null)) return null;
  let up = 0;
  let down = 0;
  for (const path of paths) {
    for (const c of path) {
      if (above !== null && c >= above) {
        up += 1;
        break;
      }
      if (below !== null && c <= below) {
        down += 1;
        break;
      }
    }
  }
  return {
    above: above === null ? null : up / n,
    below: below === null ? null : down / n,
    neither: (n - up - down) / n,
  };
}

/** The walls and, with paths (the AI view shown), which one the paths reach first by `as_of + horizon`. */
export function aheadWalls(
  zones: readonly AheadZoneIn[], price: number, paths: readonly (readonly number[])[] | null, asOf: number | null,
  horizon = AHEAD_HORIZON,
): AheadWalls {
  const w = nearestWalls(zones, price);
  const first = paths ? wallFirst(paths, w.above?.price ?? null, w.below?.price ?? null) : null;
  return {
    above: w.above,
    below: w.below,
    first,
    nPaths: first ? (paths as readonly number[][]).length : null,
    byT: asOf === null ? null : asOf + horizon * AHEAD_STEP_SEC,
    reason: w.reason,
  };
}

// ---------------------------------------------------------------- if it triggers

export interface TriggerOdds {
  nReach: number;
  reach: number;
  first: { target: number; stop: number; open: number } | null;
  /** The first `AHEAD_DRAWN_PATHS` paths' outcomes, for colouring the drawn paths. */
  perPath: AheadPathOutcome[];
}

export function pathOutcome(path: readonly number[], trigger: number, stop: number, target: number): AheadPathOutcome {
  const fill = path.findIndex((c) => c > trigger);
  if (fill < 0) return 'no';
  for (let k = fill; k < path.length; k += 1) {
    if (path[k] >= target) return 'target';
    if (path[k] <= stop) return 'stop';
  }
  return 'open';
}

export function ifTriggers(
  paths: readonly (readonly number[])[], trigger: number, stop: number, target: number,
): TriggerOdds {
  const outcomes = paths.map((p) => pathOutcome(p, trigger, stop, target));
  const count = (o: AheadPathOutcome) => outcomes.filter((x) => x === o).length;
  const nReach = outcomes.length - count('no');
  return {
    nReach,
    reach: outcomes.length ? nReach / outcomes.length : 0,
    first: nReach === 0 ? null : {
      target: count('target') / nReach, stop: count('stop') / nReach, open: count('open') / nReach,
    },
    perPath: outcomes.slice(0, AHEAD_DRAWN_PATHS),
  };
}

function laneRank(l: AheadLaneIn): { state: AheadLaneState; rank: number; levels: LevelsIn | null } | null {
  if (l.state === 'armed' || l.state === 'near') {
    return { state: l.state, rank: AHEAD_LANE_RANK[l.state], levels: l.setup };
  }
  if (AHEAD_FORMING_STATES.includes(l.state) && l.forming !== null) {
    return { state: 'forming', rank: AHEAD_LANE_RANK.forming, levels: l.forming };
  }
  return null;
}

function complete(v: LevelsIn | null): v is LevelsIn {
  return v !== null && [v.trigger, v.entry, v.stop, v.target1].every((x) => typeof x === 'number' && Number.isFinite(x));
}

function empty(family: AheadFamily, reason: string, setupType: string | null = null, state: AheadLaneState | null = null): AheadTrigger {
  return {
    family, setupType, state, provisional: state === 'forming', trigger: null, entry: null, stop: null, target: null,
    reach: null, nReach: null, first: null, perPath: null, reason,
  };
}

/**
 * The family's setup in play on the 1-minute chart (long side), and, with paths (the AI view shown), what the paths
 * do if it triggers. Rank: armed > near > forming; a tie goes to the trigger nearest the price.
 */
export function triggerRead(
  read: AheadReadIn, family: AheadFamily, price: number, paths: readonly (readonly number[])[] | null,
): AheadTrigger {
  const word = AHEAD_FAMILY_WORD[family];
  if (!read.followed) return empty(family, read.followed_note ?? AHEAD_WORDS.notFollowed);
  const names: readonly string[] = AHEAD_SETUP_FAMILIES[family];
  const lanes = read.setups.filter((l) => names.includes(l.setup_type) && (l.side ?? 'long') === 'long'
    && (l.timeframe ?? '1m') === '1m');
  let best: { lane: AheadLaneIn; state: AheadLaneState; rank: number; levels: LevelsIn | null } | null = null;
  for (const lane of lanes) {
    const r = laneRank(lane);
    if (r === null) continue;
    const dist = (x: typeof best) => (x && complete(x.levels) ? Math.abs(x.levels.trigger - price) : Infinity);
    const cand = { lane, ...r };
    if (best === null || cand.rank > best.rank || (cand.rank === best.rank && dist(cand) < dist(best))) best = cand;
  }
  if (best === null) {
    const fired = lanes.find((l) => l.state === 'triggered');
    if (fired) {
      const at = fired.setup?.triggered_at;
      return empty(family, AHEAD_WORDS.triggered(typeof at === 'number' ? etHhmm(at) : null), fired.setup_type, 'triggered');
    }
    return empty(family, AHEAD_WORDS.noLane(word));
  }
  if (!complete(best.levels)) return empty(family, AHEAD_WORDS.noLevels(word), best.lane.setup_type, best.state);
  const lv = best.levels;
  const odds = paths ? ifTriggers(paths, lv.trigger, lv.stop, lv.target1) : null;
  return {
    family,
    setupType: best.lane.setup_type,
    state: best.state,
    provisional: best.state === 'forming',
    trigger: lv.trigger,
    entry: lv.entry,
    stop: lv.stop,
    target: lv.target1,
    reach: odds ? odds.reach : null,
    nReach: odds ? odds.nReach : null,
    first: odds ? odds.first : null,
    perPath: odds ? odds.perPath : null,
    reason: null,
  };
}
