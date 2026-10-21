/**
 * What Ahead draws, decided in one pure step (ADR 065). Every gate and every sentence is here; the primitives only
 * turn prices and candle steps into pixels.
 *
 * - Nova's lines to the meet show whenever Ahead is on and the stock read has two that qualify, in every scope and
 *   every forecaster state (no AI involved).
 * - The AI view (fan, paths, odds, ghost volume, MACD fan) shows only when the answer is `ready`, the forecaster has
 *   passed its exam or the viewer switched on "Show before it has earned it", the scope is not Lines, and the chart's
 *   newest completed candle is the one the answer was made from. A forecast is never drawn over a real candle.
 * - Whenever something is not drawn, `words` says why.
 *
 * The odds and the MACD fan are memoised per (symbol, as_of, scope) and the levels they were counted against.
 */
import {
  AHEAD_COLORS,
  AHEAD_DASH,
  AHEAD_DRAWN_PATHS,
  AHEAD_HORIZON,
  AHEAD_PATH_ALPHA,
  AHEAD_SAME_PRICE,
  AHEAD_STEP_SEC,
  AHEAD_TICK_EVERY_MIN,
  AHEAD_WORDS,
  type AheadFamily,
} from './aheadConstants';
import { chartAxisClock, chartHhmm, chartSec, chartToEpoch, linesToMeet, meetTailOk, type AheadCandle } from './aheadGeometry';
import { breakWords } from './aheadBreaks';
import { aheadWalls, ifTriggers, triggerRead, type TriggerOdds } from './aheadOdds';
import type { AheadScene, AheadSceneInput, SceneBand, SceneChip, SceneLegendRow } from './aheadSceneTypes';
import type { AheadAnswer, AheadLines, AheadPathOutcome, AheadTrigger, AheadWalls } from './aheadTypes';
import { macdFan } from './macdFromPaths';

const MEMO_MAX = 64;
const memoCache = new Map<string, unknown>();

function memo<T>(key: string, make: () => T): T {
  if (memoCache.has(key)) return memoCache.get(key) as T;
  const v = make();
  memoCache.set(key, v);
  if (memoCache.size > MEMO_MAX) memoCache.delete(memoCache.keys().next().value as string);
  return v;
}

const fmt = (p: number) => (p >= 1 ? p.toFixed(2) : p.toFixed(4));

function emptyScene(on: boolean, words: string[]): AheadScene {
  return {
    on, anchorT: null, horizon: AHEAD_HORIZON, zone: null, ticks: [], fan: null, paths: [], lines: [], meet: null,
    hLines: [], chips: [], keepInView: null, ghostVolume: null, macd: null, words, legend: [], examStatus: null,
    recentVolume: [], lineRead: null, walls: null, triggers: null,
  };
}

/** Passed, on both of the forecaster's own words: the forecast's `exam_passed` and the exam itself. A pass Nova cannot
 * read the exam of is not a pass on the desk (the chip would be a bare claim). */
export function examEarned(a: AheadAnswer): boolean {
  return a.ai.exam_passed === true && a.ai.exam !== null && a.ai.exam.passed;
}

/** The forecaster's state in one sentence, and whether the AI view may be drawn. */
function aiGate(input: AheadSceneInput, anchor: AheadCandle): { word: string | null; shown: boolean } {
  const { answer: a, fetchProblem, prefs } = input;
  if (fetchProblem) return { word: fetchProblem, shown: false };
  if (prefs.scope === 'lines') return { word: AHEAD_WORDS.linesOnly, shown: false };
  if (!a) return { word: AHEAD_WORDS.asking, shown: false };
  const ai = a.ai;
  switch (ai.state) {
    case 'not_set_up': return { word: AHEAD_WORDS.notSetUp(ai.reason), shown: false };
    case 'offline': return { word: AHEAD_WORDS.offline(ai.reason), shown: false };
    case 'warming': return { word: AHEAD_WORDS.warming, shown: false };
    case 'not_enough_bars': return { word: AHEAD_WORDS.notEnoughBars(ai.need, ai.have), shown: false };
    case 'quiet': {
      const gap = a.bars.tail_gap_sec;
      return { word: AHEAD_WORDS.quiet(gap === null ? null : Math.round(gap / AHEAD_STEP_SEC)), shown: false };
    }
    case 'pending': return { word: AHEAD_WORDS.pending, shown: false };
    case 'error': return { word: AHEAD_WORDS.error(ai.reason), shown: false };
    case 'ready': break;
  }
  if (a.bar_t === null) return { word: AHEAD_WORDS.catchingUp, shown: false };
  const barT = chartSec(a.bar_t);
  if (anchor.t > barT) return { word: AHEAD_WORDS.pending, shown: false };
  if (anchor.t < barT) return { word: AHEAD_WORDS.catchingUp, shown: false };
  if (!(examEarned(a) || prefs.unearned)) {
    return { word: ai.exam_passed ? AHEAD_WORDS.hiddenExamUnread : AHEAD_WORDS.hiddenNotPassed, shown: false };
  }
  return { word: null, shown: true };
}

function examTag(a: AheadAnswer): SceneChip {
  const exam = a.ai.exam;
  if (exam !== null && examEarned(a)) {
    const text = AHEAD_WORDS.passed(exam.scope, exam.sample.days, exam.sample.moments);
    return { text, fg: AHEAD_COLORS.passedFg, bg: AHEAD_COLORS.passedBg };
  }
  const text = exam
    ? AHEAD_WORDS.notPassed(exam.volume.model.spearman, exam.volume.baseline.spearman, exam.range.model.spearman,
      exam.range.baseline.spearman, exam.band80_coverage, exam.scope)
    : a.ai.exam_passed ? AHEAD_WORDS.examUnread : AHEAD_WORDS.noExam;
  return { text, fg: AHEAD_COLORS.notPassedFg, bg: AHEAD_COLORS.notPassedBg };
}

/** The exam's status in the chart chip's opening words (the panel's cards carry it beside their AI numbers). */
export function examStatusOf(a: AheadAnswer | null): SceneChip | null {
  if (!a) return null;
  if (examEarned(a)) return { text: AHEAD_WORDS.passedTag, fg: AHEAD_COLORS.passedFg, bg: AHEAD_COLORS.passedBg };
  const text = a.ai.exam ? AHEAD_WORDS.notPassedTag : a.ai.exam_passed ? AHEAD_WORDS.examUnread : AHEAD_WORDS.noExam;
  return { text, fg: AHEAD_COLORS.notPassedFg, bg: AHEAD_COLORS.notPassedBg };
}

/** What each mark in the zone means: Nova's lines and the hatch always, the AI's marks while they are drawn. */
function legendRows(nPaths: number | null): SceneLegendRow[] {
  const rows: SceneLegendRow[] = [{ swatch: 'dash', text: AHEAD_WORDS.legendLines }];
  if (nPaths !== null) {
    rows.push(
      { swatch: 'band', text: AHEAD_WORDS.legendRange },
      { swatch: 'paths', text: AHEAD_WORDS.legendPaths(nPaths), n: nPaths },
      { swatch: 'box', text: AHEAD_WORDS.legendVolume },
    );
  }
  rows.push({ swatch: 'hatch', text: AHEAD_WORDS.legendHatch });
  return rows;
}

function ticksFrom(anchorT: number): { k: number; text: string }[] {
  const out: { k: number; text: string }[] = [];
  for (let k = 1; k <= AHEAD_HORIZON; k += 1) {
    const t = anchorT + k * AHEAD_STEP_SEC;
    if (Math.floor(t / AHEAD_STEP_SEC) % AHEAD_TICK_EVERY_MIN === 0) out.push({ k, text: chartAxisClock(t) });
  }
  return out;
}

function linesPart(lr: AheadLines | null, anchorT: number): Pick<AheadScene, 'lines' | 'meet'> {
  if (!lr || lr.state !== 'meet' || !lr.meet || lr.supportP === null || lr.resistanceP === null
    || lr.supportSlope === null || lr.resistanceSlope === null) return { lines: [], meet: null };
  const kc = lr.meet.inCandles;
  const toSteps = Math.min(kc, AHEAD_HORIZON);
  const n = Math.round(kc);
  const text = !lr.meet.withinZone
    ? AHEAD_WORDS.meetPast(n, lr.meet.t !== null ? 'min' : 'candles')
    : lr.meet.t !== null ? AHEAD_WORDS.meetAt(chartHhmm(anchorT + kc * AHEAD_STEP_SEC)) : AHEAD_WORDS.meetIn(n);
  return {
    lines: [
      { kind: 'support', fromP: lr.supportP, slope: lr.supportSlope, toSteps, color: AHEAD_COLORS.support },
      { kind: 'resistance', fromP: lr.resistanceP, slope: lr.resistanceSlope, toSteps, color: AHEAD_COLORS.resistance },
    ],
    meet: { steps: toSteps, p: lr.meet.p, text, inZone: lr.meet.withinZone },
  };
}

function withOdds(t: AheadTrigger, odds: TriggerOdds | null): AheadTrigger {
  if (!odds) return t;
  return { ...t, reach: odds.reach, nReach: odds.nReach, first: odds.first, perPath: odds.perPath };
}

function pathColor(o: AheadPathOutcome | undefined): { color: string; alpha: number } {
  if (o === 'target') return { color: AHEAD_COLORS.target, alpha: AHEAD_PATH_ALPHA.reached };
  if (o === 'stop') return { color: AHEAD_COLORS.stop, alpha: AHEAD_PATH_ALPHA.reached };
  if (o === 'open') return { color: AHEAD_COLORS.path, alpha: AHEAD_PATH_ALPHA.reached };
  return { color: AHEAD_COLORS.path, alpha: AHEAD_PATH_ALPHA.missed };
}

function wallsDrawn(w: AheadWalls, price: number): Pick<AheadScene, 'hLines' | 'chips'> {
  const hLines: AheadScene['hLines'] = [];
  const chips: AheadScene['chips'] = [];
  if (!w.first) return { hLines, chips };
  // A wall's chip carries what the paths do if it breaks, as a second line the drawing keeps only when it fits.
  const sub = (up: boolean): { sub?: string } => {
    const wall = up ? w.above : w.below;
    const b = up ? w.breaks?.above : w.breaks?.below;
    return wall && b ? { sub: AHEAD_WORDS.breakChip(breakWords(b, wall, up, w.nPaths ?? 0)) } : {};
  };
  if (w.above && w.first.above !== null) {
    hLines.push({ p: w.above.price, color: AHEAD_COLORS.wallAbove, dash: [...AHEAD_DASH.wall], chip: '' });
    chips.push({ p: w.above.price, text: AHEAD_WORDS.wallFirst(true, fmt(w.above.price), w.first.above),
      short: AHEAD_WORDS.wallFirstShort(true, w.first.above), color: AHEAD_COLORS.wallAbove, role: 'wall',
      ...sub(true) });
  }
  if (w.below && w.first.below !== null) {
    hLines.push({ p: w.below.price, color: AHEAD_COLORS.wallBelow, dash: [...AHEAD_DASH.wall], chip: '' });
    chips.push({ p: w.below.price, text: AHEAD_WORDS.wallFirst(false, fmt(w.below.price), w.first.below),
      short: AHEAD_WORDS.wallFirstShort(false, w.first.below), color: AHEAD_COLORS.wallBelow, role: 'wall',
      ...sub(false) });
  }
  // "Neither" is no one price: it asks for the middle and yields to the walls' chips (the drawing places it last).
  const mid = w.above && w.below ? (w.above.price + w.below.price) / 2 : price;
  chips.push({ p: mid, text: AHEAD_WORDS.neither(w.first.neither), short: AHEAD_WORDS.neitherShort(w.first.neither),
    color: AHEAD_COLORS.muted, role: 'neither' });
  return { hLines, chips };
}

/** Is `p` one of the walls (the setup's target sitting on the next wall reads so on its chip)? */
function isWallPrice(p: number, w: AheadWalls | null): boolean {
  return [w?.above?.price, w?.below?.price].some(x => x !== undefined && Math.abs(x - p) <= AHEAD_SAME_PRICE);
}

function strategyDrawn(t: AheadTrigger, w: AheadWalls | null): Pick<AheadScene, 'hLines' | 'chips'> {
  const hLines: AheadScene['hLines'] = [];
  const chips: AheadScene['chips'] = [];
  if (t.trigger === null || t.stop === null || t.target === null) return { hLines, chips };
  const dash = [...AHEAD_DASH.strategy];
  hLines.push({ p: t.trigger, color: AHEAD_COLORS.trigger, dash, chip: AHEAD_WORDS.buyStop(fmt(t.trigger)) });
  hLines.push({ p: t.stop, color: AHEAD_COLORS.stop, dash, chip: AHEAD_WORDS.stopAt(fmt(t.stop)) });
  const targetWords = isWallPrice(t.target, w) ? AHEAD_WORDS.targetAtWall : AHEAD_WORDS.targetAt;
  hLines.push({ p: t.target, color: AHEAD_COLORS.target, dash, chip: targetWords(fmt(t.target)) });
  if (t.first) {
    chips.push({ p: t.target, text: AHEAD_WORDS.targetFirst(t.first.target),
      short: AHEAD_WORDS.targetFirstShort(t.first.target), color: AHEAD_COLORS.target });
    chips.push({ p: t.stop, text: AHEAD_WORDS.stopFirst(t.first.stop), short: AHEAD_WORDS.stopFirstShort(t.first.stop),
      color: AHEAD_COLORS.stop });
  }
  return { hLines, chips };
}

function keepInView(s: Pick<AheadScene, 'fan' | 'meet' | 'lines' | 'hLines'>): AheadScene['keepInView'] {
  const ps: number[] = [];
  for (const b of s.fan ?? []) ps.push(b.q10, b.q90);
  if (s.meet?.inZone) ps.push(s.meet.p);
  for (const l of s.lines) ps.push(l.fromP, l.fromP + l.slope * l.toSteps);
  for (const h of s.hLines) ps.push(h.p);
  const finite = ps.filter((p) => Number.isFinite(p));
  return finite.length ? { lo: Math.min(...finite), hi: Math.max(...finite) } : null;
}

export function aheadScene(input: AheadSceneInput): AheadScene {
  const { prefs, read, candles, symbol } = input;
  if (!prefs.shown) return emptyScene(false, []);
  if (!input.paneIs1m) return emptyScene(false, [AHEAD_WORDS.onlyOneMinute]);
  const roomWords = input.roomOk ? [] : [AHEAD_WORDS.noRoom];
  const anchor = candles.length ? candles[candles.length - 1] : null;
  if (anchor === null) {
    return emptyScene(true, [...roomWords, input.replayEmpty ? AHEAD_WORDS.replayEmpty(symbol) : AHEAD_WORDS.noCandles]);
  }
  const gate = aiGate(input, anchor);
  const a = gate.shown ? input.answer : null;
  const scope = prefs.scope;
  const asOf = (a?.as_of ?? chartToEpoch(anchor.t) + AHEAD_STEP_SEC);
  const paths = a?.ai.paths?.close ?? null;
  // The walls' side and the odds are counted from where the paths start: the answer's own close (the chart's close,
  // painted with the live tick, can sit on the other side of a wall edge). With no AI view, the chart's close.
  const price = a?.price ?? anchor.c;
  const memoKey = `${symbol}|${a?.as_of ?? 'none'}|${scope}`;
  const later: string[] = [];

  let lineRead: AheadLines | null = null;
  let walls: AheadWalls | null = null;
  let triggers: AheadScene['triggers'] = null;
  if (read === null) {
    later.push(AHEAD_WORDS.readLoading);
  } else {
    const tailOk = meetTailOk(a ? a.bars.contiguous_tail : null, candles);
    lineRead = linesToMeet(read.level_map?.lines?.one_minute ?? [], candles, tailOk);
    if (lineRead.reason) later.push(lineRead.reason);
    const zones = read.level_map?.intraday ?? [];
    const near = aheadWalls(zones, price, null, asOf);
    // Keyed by every zone's edges: the next wall beyond each one counts in its "if it breaks".
    const edges = zones.map((z) => `${z.id}:${z.lo}-${z.hi}:${z.members.map((m) => m.kind).join('+')}`).join(',');
    walls = paths
      ? memo(`${memoKey}|walls|${price}|${edges}`, () => aheadWalls(zones, price, paths, asOf))
      : near;
    const fam = (f: AheadFamily) => {
      const t = triggerRead(read, f, price, null);
      if (!paths || t.trigger === null || t.stop === null || t.target === null) return t;
      const [tr, st, tg] = [t.trigger, t.stop, t.target];
      return withOdds(t, memo(`${memoKey}|${f}|${tr}|${st}|${tg}`, () => ifTriggers(paths, tr, st, tg)));
    };
    triggers = { flat_top: fam('flat_top'), first_pullback: fam('first_pullback') };
  }

  let drawn: Pick<AheadScene, 'hLines' | 'chips'> = { hLines: [], chips: [] };
  if (scope === 'all' && walls && a) {
    drawn = wallsDrawn(walls, price);
    if (walls.reason) later.push(walls.reason);
  } else if ((scope === 'flat_top' || scope === 'first_pullback') && triggers) {
    drawn = strategyDrawn(triggers[scope], walls);
    if (triggers[scope].reason) later.push(triggers[scope].reason as string);
  }

  const fan: SceneBand[] | null = a?.ai.close
    ? a.ai.close.map((r, i) => ({ k: i + 1, q10: r[0], q25: r[1], q50: r[2], q75: r[3], q90: r[4] }))
    : null;
  const perPath = scope === 'flat_top' || scope === 'first_pullback' ? triggers?.[scope].perPath ?? null : null;
  const drawnPaths = (paths ?? []).slice(0, AHEAD_DRAWN_PATHS).map((points, j) => ({
    points: [...points],
    ...(perPath ? pathColor(perPath[j]) : { color: AHEAD_COLORS.path, alpha: AHEAD_PATH_ALPHA.all }),
  }));
  const ghostVolume = a?.ai.volume ? a.ai.volume.map((r, i) => ({ k: i + 1, q10: r[0], q50: r[2], q90: r[4] })) : null;
  const macd = paths && input.macdOn
    ? memo(`${memoKey}|macd|${candles.length}|${anchor.t}|${anchor.c}`, () => macdFan(candles.map((c) => c.c), paths))
    : null;
  const lm = linesPart(lineRead, anchor.t);
  const tags: SceneChip[] = [{ text: AHEAD_WORDS.aiTag, fg: AHEAD_COLORS.aiTagFg, bg: AHEAD_COLORS.aiTagBg }];
  if (a) tags.push(examTag(a));
  const scene: AheadScene = {
    on: true,
    anchorT: anchor.t,
    horizon: AHEAD_HORIZON,
    zone: { title: AHEAD_WORDS.zoneTitle, tags, nowText: AHEAD_WORDS.now(chartHhmm(anchor.t + AHEAD_STEP_SEC)) },
    ticks: ticksFrom(anchor.t),
    fan,
    paths: drawnPaths,
    ...lm,
    ...drawn,
    keepInView: keepInView({ fan, ...lm, hLines: drawn.hLines }),
    ghostVolume,
    macd,
    words: [...roomWords, ...(gate.word ? [gate.word] : []), ...later],
    legend: legendRows(a?.ai.paths ? a.ai.paths.n : null),
    examStatus: examStatusOf(input.answer),
    recentVolume: input.recentVolume ?? [],
    lineRead,
    walls,
    triggers,
  };
  return input.roomOk ? scene : withoutDrawing(scene);
}

/** No room at the edge: nothing of the zone is drawn (a forecast clipped at the edge would read as a whole one) and
 * nothing stretches the price scale; the words say why, and the panel keeps its numbers. */
function withoutDrawing(scene: AheadScene): AheadScene {
  return { ...scene, zone: null, ticks: [], fan: null, paths: [], lines: [], meet: null, hLines: [], chips: [],
    keepInView: null, ghostVolume: null, macd: null };
}

/** Tests only. */
export function clearAheadSceneMemo(): void {
  memoCache.clear();
}
