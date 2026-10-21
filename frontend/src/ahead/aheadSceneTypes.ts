/** Ahead (ADR 061): what the chart draws, decided in one pure step (`aheadScene.ts`) and drawn by the primitives.
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

export interface SceneBand {
  k: number;
  q10: number;
  q25: number;
  q50: number;
  q75: number;
  q90: number;
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
  /** Minute labels inside the pane bottom, every 5 minutes. */
  ticks: { k: number; text: string }[];
  /** The forecaster's 50% / 80% price bands per step; null unless the AI view is shown. */
  fan: SceneBand[] | null;
  /** At most 16 drawn paths (closes per step). */
  paths: { points: number[]; color: string; alpha: number }[];
  /** Nova's own lines carried on from the anchor (no AI): price at the anchor, slope per candle, how far to draw. */
  lines: { kind: 'support' | 'resistance'; fromP: number; slope: number; toSteps: number; color: string }[];
  /** Where they meet (clipped at the zone edge with words when it is further). */
  meet: { steps: number; p: number; text: string; inZone: boolean } | null;
  /** Horizontal stubs inside the zone: the walls (scope All) or trigger / stop / target (a strategy scope). */
  hLines: { p: number; color: string; dash: number[]; chip: string }[];
  /** Odds chips anchored at a price, drawn at the zone's right edge. */
  chips: { p: number; text: string; color: string }[];
  /** The price range the drawn parts need on the scale; null when nothing price-bearing is drawn. */
  keepInView: { lo: number; hi: number } | null;
  /** Ghost volume per step (q10 / q50 / q90); null unless the AI view is shown. */
  ghostVolume: { k: number; q10: number; q50: number; q90: number }[] | null;
  /** The MACD line's fan per step, computed from the paths; null unless shown and the MACD pane is on. */
  macd: SceneBand[] | null;
  /** State sentences for the heading; the first is the main one. Empty when everything is drawn. */
  words: string[];
  /** The legend strip under the zone; null when the AI view is not shown. */
  legend: string | null;
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
}
