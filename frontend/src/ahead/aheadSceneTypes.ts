/** Ahead (ADR 065): what the chart draws, decided in one pure step (`aheadScene.ts`) and drawn by the primitives.
 *
 * Every gate and every word is decided when the scene is built; the primitives only turn prices and candle steps
 * into pixels. Times here are CHART seconds (Eastern wall time read as UTC, `etChartSeconds`), the same clock the
 * candle series uses. A step `k` is `k` candles after the anchor candle; the primitives place it at
 * `logicalToCoordinate(indexOf(anchorT) + k)`.
 */
import type { AheadAnswer, AheadLines, AheadPrefs, AheadTrigger, AheadWalls } from './aheadTypes';
import type { StockRead } from '../stock_read';

export interface SceneChip {
  text: string;
  fg: string;
  bg: string;
}

/** What an odds chip stands for (`AheadScene.chips`). */
export type SceneChipRole = 'wall' | 'neither' | 'story';

export interface SceneBand {
  k: number;
  q10: number;
  q25: number;
  q50: number;
  q75: number;
  q90: number;
}

/** One row of the legend the Ahead panel shows (`AheadSheet`): the swatch drawn and its words. */
export interface SceneLegendRow {
  /** `paths`: the soft cloud; `story`: the story paths; `marks`: their fill / exit / wall marks. */
  swatch: 'dash' | 'band' | 'paths' | 'story' | 'marks' | 'box' | 'hatch';
  text: string;
  /** The cloud and story rows: how many paths the forecaster drew (the chart Key's words count them). */
  n?: number;
  /** The story and marks rows on scope All: the high / middle / low cases and their wall rings (not a trade's). */
  cases?: boolean;
}

/** One stretch of a story path in one stage, in steps from the anchor (0) to the horizon; fractional where a close
 * crosses a level between two whole steps. */
export interface StorySegment {
  from: number;
  to: number;
  color: string;
  alpha: number;
}

/** A mark on a story path at step `k` (fractional), price `p`: the buy-stop's fill, a target or stop exit, or the
 * first wall it reaches (scope All, a filled diamond). */
export interface StoryMark {
  k: number;
  p: number;
  kind: 'fill' | 'target' | 'stop' | 'wall';
  color: string;
}

/** One of the (at most three) story paths drawn over the cloud, chosen by rule (`aheadStory.ts`). */
export interface SceneStory {
  /** The price it starts from at step 0: the price its crossings were counted from (the answer's `price`). It is
   * drawn from there, not from the anchor candle's close, so a fractional crossing lands on the line and the level. */
  start: number;
  /** Its closes per step (step k is `points[k - 1]`). */
  points: readonly number[];
  /** Grey / coloured / faded stretches, end to end from step 0 to the horizon. */
  segments: StorySegment[];
  marks: StoryMark[];
  /** Its end label, shorter words for a narrower zone, and the odds only for a narrow one (`AHEAD_WORDS.story*`). */
  label: string;
  short: string;
  tiny: string;
  /** The label's colour: the group's (or the wall's it reached), grey for neither. */
  color: string;
}

export interface AheadScene {
  /** The switch is on and this pane is a 1-minute pane. False: draw nothing, ask nothing. */
  on: boolean;
  /** The newest completed candle everything hangs from (chart seconds); null: nothing to anchor to. */
  anchorT: number | null;
  /** Steps in the zone (15). */
  horizon: number;
  /** The hatched zone and its heading; null when there is no anchor. */
  zone: { title: string; tags: SceneChip[]; nowText: string } | null;
  /** Minute labels every 5 minutes, on the time axis under the zone. */
  ticks: { k: number; text: string }[];
  /** The forecaster's 50% / 80% price bands per step; null unless the AI view is shown. */
  fan: SceneBand[] | null;
  /** Every path the forecaster drew (closes per step), drawn as one faint cloud with no outcome colour; empty unless
   * the AI view is shown. */
  cloud: readonly (readonly number[])[];
  /** At most three story paths drawn over the cloud, coloured by trade stage (or by the first wall on scope All). */
  story: SceneStory[];
  /** Nova's own lines carried on from the anchor (no AI): price at the anchor, slope per candle, how far to draw. */
  lines: { kind: 'support' | 'resistance'; fromP: number; slope: number; toSteps: number; color: string }[];
  /** Where they meet (clipped at the zone edge with words when it is further). */
  meet: { steps: number; p: number; text: string; inZone: boolean } | null;
  /** Horizontal stubs inside the zone: the walls (scope All) or trigger / stop / target (a strategy scope). */
  hLines: { p: number; color: string; dash: number[]; chip: string }[];
  /** Odds chips anchored at a price, drawn at the zone's right edge; `short` (then `tiny`, when given) when the zone
   * is too narrow for `text`. A chip never leaves the zone. `sub`: a wall's "if it breaks" second line, longest words
   * first, drawn only when one fits (the panel's walls card always carries it). `role`: 'wall' -- a wall's chip,
   * placed first on its wall's price; 'neither' -- tied to no one price, placed next in the free space between the
   * walls; 'story' -- the end label of story path `story` (its index in `story`), placed last beside its path's end
   * (it yields to the odds chips); absent -- a strategy's chip on its own price. */
  chips: {
    p: number; text: string; short: string; tiny?: string; color: string; sub?: readonly string[];
    role?: SceneChipRole; story?: number;
  }[];
  /** The price range the drawn parts need on the scale; null when nothing price-bearing is drawn. */
  keepInView: { lo: number; hi: number } | null;
  /** Ghost volume per step (q10 / q50 / q90); null unless the AI view is shown. */
  ghostVolume: { k: number; q10: number; q50: number; q90: number }[] | null;
  /** The MACD line's fan per step, computed from the paths; null unless shown and the MACD pane is on. */
  macd: SceneBand[] | null;
  /** State sentences for the heading; the first is the main one. Empty when everything is drawn. */
  words: string[];
  /** What each mark in the zone means, for the Ahead panel (never drawn over the chart). */
  legend: SceneLegendRow[];
  /** The exam's status in the chart chip's own words, short (the panel's cards carry it); null with no answer. */
  examStatus: SceneChip | null;
  /** The last real completed 1-minute volumes, oldest first (the panel's volume chart). */
  recentVolume: number[];
  /** The numbers the Ahead panel shows, worked out once with the scene. */
  lineRead: AheadLines | null;
  walls: AheadWalls | null;
  triggers: { flat_top: AheadTrigger; first_pullback: AheadTrigger } | null;
}

/** Everything the scene needs; no fetching happens while building it. */
export interface AheadSceneInput {
  symbol: string;
  prefs: AheadPrefs;
  /** Is this pane the 1-minute one? */
  paneIs1m: boolean;
  answer: AheadAnswer | null;
  /** Words when the last fetch failed (404 before an API restart, unreachable); null otherwise. */
  fetchProblem: string | null;
  /** The stock read the Trader page already holds (Nova's lines, zones and setup lanes); null while loading. */
  read: StockRead | null;
  /** The chart's COMPLETED candles, oldest first, in chart seconds (the forming candle excluded). */
  candles: { t: number; c: number }[];
  /** Is the MACD pane showing? (No MACD fan without it.) */
  macdOn: boolean;
  /** False when the zone has no room at the right edge (the operator owns the view). */
  roomOk: boolean;
  /** A replay desk with no candles for this symbol. */
  replayEmpty: boolean;
  /** The last real completed 1-minute volumes, oldest first; empty when the pane has no volume series. */
  recentVolume?: number[];
}
