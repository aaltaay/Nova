/** The day's support and resistance on the wire (ADR 036 amendment 2026-09-30): the read's `level_map`
 * and the plan's `levels` (AGENTS.md §3, "The day's levels"). */
import type { ReadState } from './types';

/** One reason a price holds (ADR 036 amendment 2026-09-30): a high of day, a top tested N times, a
 * half or whole dollar, a daily high touched twice... `times` are an intraday level's tests (epoch
 * seconds), `dates` a daily level's sessions. */
export type LevelKind =
  | 'hod' | 'lod' | 'pmh' | 'open' | 'vwap' | 'top' | 'bottom' | 'whole' | 'half' | 'yday_high' | 'yday_low'
  | 'prior_close' | 'daily_highs' | 'daily_lows' | 'daily_high' | 'gap' | 'sma200';

export interface LevelMember {
  kind: LevelKind;
  price: number;
  label: string;
  touches: number | null;
  times: number[];
  dates: string[];
  note: string | null;
}

/** Levels close together, as one zone that lists every reason it holds. */
export interface LevelZone {
  id: string;
  lo: number;
  hi: number;
  /** The zone's edge nearest the price. */
  price: number;
  side: 'above' | 'below' | 'at' | 'unknown';
  strength: number;
  label: string;
  tag: string;
  /** The candles it was read from: the session's 1-minute, its 5-minute, or past days. */
  home: 'intraday' | 'five_minute' | 'daily';
  members: LevelMember[];
}

/** What the level study measured, each pair (at the level, at a random price) in percent. */
export interface LevelStudy {
  source: string;
  round_turn: [number, number];
  round_through: [number, number];
  round_lost: [number, number];
  hod_past: [number, number];
  top_past: [number, number];
  daily_past: [number, number];
}

/** Today's map from 1-minute candles (the plan's, and the 1-minute pane's nearest tops and bottoms),
 * the day from 5-minute candles (the 5-minute pane; null from a backend older than it) and the daily
 * map (Full Day). */
export interface LevelMap {
  schema_version: number;
  price: number | null;
  intraday: LevelZone[];
  five_minute: LevelZone[] | null;
  daily: LevelZone[];
  daily_sessions: number;
  daily_error: string | null;
  study: LevelStudy | null;
}

export interface PlanLevelNote {
  state: ReadState;
  text: string;
  detail: string | null;
}

/** A zone of today's map between the plan's stop and target. */
export interface PlanBetween {
  price: number;
  lo: number;
  hi: number;
  tag: string;
  label: string;
  round: boolean;
  hod: boolean;
}

/** What the plan says about the day's levels: Room (a warning while trial T7 runs), the round at the
 * target and at the stop, the next round, a round just broken or lost, and the levels in between. */
export interface PlanLevels {
  room: PlanLevelNote & { r: number | null; price: number | null; trial: string };
  target: PlanLevelNote | null;
  stop: PlanLevelNote | null;
  next: PlanLevelNote | null;
  recent: PlanLevelNote | null;
  between: PlanBetween[];
}
