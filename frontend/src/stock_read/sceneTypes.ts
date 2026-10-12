/**
 * What a chart pane's stock-read scene holds (ADR 036): the shapes `chartShapes.ts` decides on, in prices and
 * bar times, for `SetupShapesPrimitive` to map onto the pane and `sceneRender.ts` to draw.
 */
import type { ISeriesApi, SeriesType, Time } from 'lightweight-charts';
import type { SceneLevel, SceneTick } from './levelRender';
import type { LabelDetail, LabelShrink } from './sceneLabels';

export interface SceneBox {
  t1: Time;
  /** Null runs to the pane's right edge. */
  t2: Time | null;
  p1: number;
  p2: number;
  fill: string;
  stroke: string | null;
  dashed: boolean;
  label: string | null;
  labelColor: string;
  /** The label under the box (a consolidation's), so it never sits on its leg's. */
  labelBelow?: boolean;
  /** A label that makes room (a past setup's): its shorter forms and its claim to the room. Without it
   * the label is drawn whole where it is (a live lane's). */
  shrink?: LabelShrink;
  /** What the pane reports as hovered over this box (`hitTest`): a lane's or a past setup's story. */
  hoverId?: string;
}

export interface SceneSegment {
  /** Null starts at the pane's left edge. */
  t1: Time | null;
  price: number;
  color: string;
  dashed: boolean;
  label: string | null;
}

export interface SceneVLine {
  t: Time;
  color: string;
  label: string | null;
}

export interface SceneEdgeTag {
  price: number;
  label: string;
  color: string;
  /** A tag and a word with one id name one line: the word's own tag stands for both. */
  id?: string;
}

/** A line's tag in the edge column: a price line's (fixed `price`) or a series' (its value on the pane's last
 * visible bar, as lightweight-charts places a series title). */
export interface SceneWord {
  id: string;
  text: string;
  color: string;
  priority: number;
  price: number | null;
  series: ISeriesApi<SeriesType> | null;
  /** Out of view its tag adds the value; false when the text already says it. */
  valueWhenOff: boolean;
  /** `plain`: coloured words on dark, with no line of their own (a forming setup's prices); else the line's own tag. */
  style?: 'filled' | 'plain';
}

/** Room at the right edge something else holds (the position tag): the column keeps clear of it. */
export interface SceneReserve {
  price: number;
  height: number;
}

/** A candle marked over `price`: a day's +40% run (an arrow pointing down at the high) or a flat top's break (`up`:
 * a triangle pointing up over the breaking candle), and its label, which makes room. */
export interface SceneMark {
  t: Time;
  price: number;
  label: string;
  color: string;
  /** Higher keeps its label where marks crowd. */
  rank: number;
  /** Which way the triangle points; down by default. */
  dir?: 'up' | 'down';
}

/** A ring on one candle at a price -- a flat top's touch (2026-10-06) -- and a label over it, which stays put. */
export interface SceneDot {
  t: Time;
  price: number;
  /** The ring's outline, and its fill. */
  color: string;
  fill: string;
  label?: string | null;
  labelColor?: string;
  /** What the pane reports as hovered over the ring: its setup's story. */
  hoverId?: string;
}

/** A trend line (ADR 036 amendment 2026-10-12): straight from its first touch to its last, dashed on to the pane's
 * newest candle; a ring on each touch and a cross on the candle that closed through it. */
export interface SceneTrend {
  t1: Time;
  p1: number;
  t2: Time;
  p2: number;
  /** Where it runs at the last closed candle; `slope` a candle carries it on to the pane's newest candle. */
  tEnd: Time;
  pEnd: number;
  slope: number;
  color: string;
  /** A broken line: faint and dashed. */
  faded: boolean;
  touches: { t: Time; price: number }[];
  broke: { t: Time; price: number } | null;
  /** Its name in the edge column, at its price on the newest candle, in `labelColor` (a broken line's stays readable). */
  label: string;
  labelColor: string;
  hoverId: string;
  priority: number;
}

/** A filled tag over a price on one candle, on a stem down to the price. */
export interface ScenePin {
  t: Time;
  price: number;
  label: string;
  color: string;
}

/** Where a boxed plan's setup stands: forming draws the faint box, the rest the box in full colour. */
export type StrategyState = 'forming' | 'near' | 'armed' | 'triggered';

/** A setup's plan as one box from its stop to target 1, right of the newest candle to the pane's edge (operator asks
 * 2026-10-12): faint while the setup is only forming -- from its window while that is ahead and on the pane, else
 * waiting at the right edge -- and in full colour once it is near, armed or triggered. Its name and where it stands
 * are in it, its prices the edge column's words (and, once armed, the axis's), target 2 a dash over it in view, else a
 * small arrow past target 1. */
export interface SceneStrategy {
  /** The newest candle: the box starts after it. */
  after: Time;
  /** Candles from `after` to the window's start while the window is ahead, else null; and to its end, null without one. */
  startBars: number | null;
  endBars: number | null;
  entry: number;
  stop: number;
  target: number;
  target2: number | null;
  side: 'long' | 'short';
  state: StrategyState;
  /** "GAP AND GO", then "strategy" (forming) or where it stands ("armed") after it where the room allows. */
  name: string;
  word: string;
  /** Its window where the box stands on it ("09:30–10:00", "until 11:30"; empty without one), and where it waits at
   * the edge ("from 09:30 →"); once armed, when ("since 09:34", "at 09:36", with "until 10:00" while a window is
   * open). */
  when: string;
  whenWaiting: string;
}

/** Where in a candle a moment falls: the candle, and how far through it (0 its left edge, 1 its right). */
export interface SceneAt {
  t: Time;
  frac: number;
}

/** One stretch of Nova's LULD band (ADR 047 amendment 2026-10-12): from the moment it began to the next one. */
export interface SceneLuldStep {
  from: SceneAt;
  to: SceneAt;
  lower: number | null;
  upper: number | null;
  /** Approximate (Nova did not see the stock open or reopen, or guessed its tier): dashed. */
  approx: boolean;
}

/** Nova's LULD band on the 1-minute chart (`luldShapes.ts`): a line above and below the candles that steps where the
 * band moved. */
export interface SceneLuld {
  steps: SceneLuldStep[];
  color: string;
}

export interface Scene {
  boxes: SceneBox[];
  segments: SceneSegment[];
  vlines: SceneVLine[];
  edgeTags: SceneEdgeTag[];
  pins: ScenePin[];
  /** Prices the pane's autoscale must keep in view (the plan's stop and target). */
  keepInView: { min: number; max: number } | null;
  /** How much a past setup's label says. */
  labels: LabelDetail;
  /** The day's levels with a line, and the rest as ticks on the price axis (`levelRender.ts`). */
  levels?: SceneLevel[];
  ticks?: SceneTick[];
  /** The lines' tags the edge column places with the levels' names. */
  words?: SceneWord[];
  reserves?: SceneReserve[];
  /** The pane's top pixels its corner chips cover at the right edge: the column starts under them. */
  topInset?: number;
  marks?: SceneMark[];
  /** The flat tops' touches. */
  dots?: SceneDot[];
  /** The chart's trend lines. */
  trends?: SceneTrend[];
  /** A setup's plan with only the plan behind it, in place of zones and lines across the pane (1-minute pane). */
  strategy?: SceneStrategy | null;
  /** Nova's LULD band (1-minute pane). */
  luld?: SceneLuld | null;
}

export const EMPTY_SCENE: Scene = {
  boxes: [], segments: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: 'compact',
};
