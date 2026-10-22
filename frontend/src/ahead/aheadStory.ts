/**
 * Ahead's story paths (ADR 065): at most three of the forecaster's paths drawn over the soft cloud of them all, chosen
 * by rule (never by hand) and coloured by what is happening on them, so one line never reads as a trade that survived
 * a dive it took before it was ever filled. Pure; built once per answer and scope in the scene's memo.
 *
 * - A strategy scope: one path per outcome group of "if it triggers" (`aheadOdds.pathTrade`) -- target first, stop
 *   first, and still open (never filled when no path that fills stays open) -- each the group's most typical member:
 *   the path nearest (mean absolute distance) the group's per-step median. A group with no path is skipped. Grey before
 *   the fill, the outcome's colour from the fill to the exit, faded after it; a dot at the fill, ✓ / ✕ at the exit.
 * - Scope All: a high, a middle and a low case -- the paths whose final close ranks nearest 90%, 50% and 10% of all
 *   final closes. Grey until the first wall it reaches (`aheadOdds.wallTouch`), then that wall's colour, with a
 *   filled diamond there; a path that reaches neither stays grey.
 *
 * Steps run from the anchor (0) to the horizon. A level crossed between two whole steps is placed by interpolating the
 * two closes (the start price before step 1), so the dot sits where the line meets the level.
 */
import { AHEAD_COLORS, AHEAD_STORY_ALPHA, AHEAD_STORY_CASES, AHEAD_WORDS } from './aheadConstants';
import { pathTrade, wallTouch } from './aheadOdds';
import type { SceneStory, StoryMark, StorySegment } from './aheadSceneTypes';
import type { AheadPathOutcome } from './aheadTypes';

type Paths = readonly (readonly number[])[];

/** Where the path crosses `level` on its way to the close at index `i` (step `i + 1`), as a fractional step between
 * step `i` and step `i + 1`; `start` is the price at step 0. */
export function crossingStep(path: readonly number[], start: number, i: number, level: number): number {
  const prev = i === 0 ? start : path[i - 1];
  const cur = path[i];
  if (cur === prev) return i + 1;
  return i + Math.min(1, Math.max(0, (level - prev) / (cur - prev)));
}

/** The member nearest the group's per-step median (mean absolute distance); a tie goes to the first. */
export function typicalMember(paths: Paths, members: readonly number[]): number {
  const steps = Math.min(...members.map((j) => paths[j].length));
  const median: number[] = [];
  for (let k = 0; k < steps; k += 1) {
    const vs = members.map((j) => paths[j][k]).sort((a, b) => a - b);
    const m = vs.length >> 1;
    median.push(vs.length % 2 ? vs[m] : (vs[m - 1] + vs[m]) / 2);
  }
  let best = members[0];
  let bestD = Infinity;
  for (const j of members) {
    let d = 0;
    for (let k = 0; k < steps; k += 1) d += Math.abs(paths[j][k] - median[k]);
    d /= Math.max(steps, 1);
    if (d < bestD) {
      bestD = d;
      best = j;
    }
  }
  return best;
}

/** Grey to `on`, `color` from `on` to `off` (the horizon with none), faded after; empty stretches left out. */
export function stages(horizon: number, color: string, on: number | null, off: number | null): StorySegment[] {
  const grey = { color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before };
  if (on === null) return [{ from: 0, to: horizon, ...grey }];
  const end = off ?? horizon;
  return [
    { from: 0, to: on, ...grey },
    { from: on, to: end, color, alpha: AHEAD_STORY_ALPHA.during },
    { from: end, to: horizon, color, alpha: AHEAD_STORY_ALPHA.after },
  ].filter((s) => s.to > s.from);
}

type Words = (share: number) => string;
const W = AHEAD_WORDS;
const GROUP: Record<AheadPathOutcome, { color: string; label: Words; short: Words; tiny: Words }> = {
  target: { color: AHEAD_COLORS.target, label: W.storyTarget, short: W.storyTargetShort, tiny: W.storyTargetTiny },
  stop: { color: AHEAD_COLORS.stop, label: W.storyStop, short: W.storyStopShort, tiny: W.storyStopTiny },
  open: { color: AHEAD_COLORS.path, label: W.storyOpen, short: W.storyOpenShort, tiny: W.storyOpenTiny },
  no: { color: AHEAD_COLORS.muted, label: W.storyNever, short: W.storyNeverShort, tiny: W.storyNeverTiny },
};

/** A strategy's story paths: one per outcome group of "if it triggers", in the order target, stop, open (or never). */
export function strategyStory(paths: Paths, start: number, trigger: number, stop: number,
  target: number): SceneStory[] {
  const trades = paths.map((p) => pathTrade(p, trigger, stop, target));
  const filled = trades.filter((t) => t.outcome !== 'no').length;
  const groupOf = (o: AheadPathOutcome) => trades.flatMap((t, j) => (t.outcome === o ? [j] : []));
  const order: AheadPathOutcome[] = ['target', 'stop', groupOf('open').length ? 'open' : 'no'];
  const out: SceneStory[] = [];
  for (const o of order) {
    const members = groupOf(o);
    if (members.length === 0) continue;
    const j = typicalMember(paths, members);
    const path = paths[j];
    const tr = trades[j];
    const g = GROUP[o];
    // The group's share of the paths that fill; "never fills" is a share of every path.
    const share = o === 'no' ? members.length / paths.length : members.length / filled;
    const marks: StoryMark[] = [];
    let fillK: number | null = null;
    let exitK: number | null = null;
    if (o !== 'no') {
      fillK = crossingStep(path, start, tr.fill, trigger);
      marks.push({ k: fillK, p: trigger, kind: 'fill', color: AHEAD_COLORS.trigger });
      if (o === 'target' || o === 'stop') {
        const level = o === 'target' ? target : stop;
        exitK = Math.max(fillK, crossingStep(path, start, tr.exit, level));
        marks.push({ k: exitK, p: level, kind: o, color: g.color });
      }
    }
    out.push({ start, points: path, segments: stages(path.length, g.color, fillK, exitK), marks, label: g.label(share),
      short: g.short(share), tiny: g.tiny(share), color: g.color });
  }
  return out;
}

/** Scope All's story paths: the high, middle and low cases by final close, each coloured from the first wall it
 * reaches. `above` / `below`: the drawn walls' prices (null: none drawn). */
export function caseStory(paths: Paths, start: number, above: number | null, below: number | null): SceneStory[] {
  const n = paths.length;
  if (n === 0) return [];
  const last = (j: number) => paths[j][paths[j].length - 1];
  const ranked = paths.map((_, j) => j).sort((a, b) => last(a) - last(b) || a - b);
  const used = new Set<number>();
  const out: SceneStory[] = [];
  AHEAD_STORY_CASES.forEach((q, i) => {
    const j = ranked[Math.round(q * (n - 1))];
    if (used.has(j)) return;
    used.add(j);
    const path = paths[j];
    const touch = wallTouch(path, above, below);
    const level = touch.side === 'above' ? above : touch.side === 'below' ? below : null;
    const color = touch.side === 'above' ? AHEAD_COLORS.wallAbove
      : touch.side === 'below' ? AHEAD_COLORS.wallBelow : AHEAD_COLORS.muted;
    const k = level === null ? null : crossingStep(path, start, touch.at, level);
    const marks: StoryMark[] = k === null || level === null ? [] : [{ k, p: level, kind: 'wall', color }];
    out.push({ start, points: path, segments: stages(path.length, color, k, null), marks,
      label: AHEAD_WORDS.storyCase[i], short: AHEAD_WORDS.storyCaseShort[i], tiny: AHEAD_WORDS.storyCaseShort[i],
      color });
  });
  return out;
}
