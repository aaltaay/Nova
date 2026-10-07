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

/** A filled tag over a price on one candle, on a stem down to the price. */
export interface ScenePin {
  t: Time;
  price: number;
  label: string;
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
}

export const EMPTY_SCENE: Scene = {
  boxes: [], segments: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: 'compact',
};
