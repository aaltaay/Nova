/**
 * The three lanes on the wire (ADR 071): `GET /api/ibkr/lanes` and `/api/ibkr/status` `lanes` / `recording_switch`.
 *
 * A lane is one Level 2 line and one Time & Sales line on one stock; the owners are you, Claude's seat and the
 * brain (ADR 072 decision 10: the brain names lane 3's stock; the bots' setup picker is gone). A pane on a stock no
 * lane is on waits for one (laneWait.ts) and asks this view when one came. Records and the REC chips read who
 * records what from the same view. Read at the boundary: a malformed lane is an empty one, an unknown field is
 * dropped, and nothing is invented. Version 1 of the view carried lane 3 as `bots` with the picker's fields: an
 * older backend's answer still parses, and the brain's lane reads empty.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constantGroups/chart_api';
import { LANES_PATH } from '../constantGroups/market_ui';
import type { AutoRecordSwitch } from './types';

export type LaneOwner = 'you' | 'claude' | 'brain';
export const LANE_OWNERS: readonly LaneOwner[] = ['you', 'claude', 'brain'];

export interface Lane {
  symbol: string | null;
  since: number | null;
  /** The Level 2 line is up. */
  depth: boolean;
  /** The Time & Sales line is up. */
  tape: boolean;
  /** Nova records the lane's stock now. */
  recording: boolean;
  /** Why a line of the lane's stock did not open. */
  error: string | null;
}

/** The brain's lane (lane 3): the one stock the brain named, and its own words for naming it. */
export interface BrainLane extends Lane {
  why: string | null;
}

export interface LanesView {
  schema_version: number;
  you: Lane;
  claude: Lane;
  brain: BrainLane;
  /** The lanes' recording could not start or stop a recording, and why. */
  recording_error: string | null;
}

type Loose = Record<string, unknown>;

const isObject = (v: unknown): v is Loose => v != null && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const sym = (v: unknown): string | null => str(v)?.toUpperCase() ?? null;

function lane(v: unknown): Lane {
  const r = isObject(v) ? v : {};
  return {
    symbol: sym(r.symbol), since: num(r.since), depth: r.depth === true, tape: r.tape === true,
    recording: r.recording === true, error: str(r.error),
  };
}

function brainLane(v: unknown): BrainLane {
  const r = isObject(v) ? v : {};
  return { ...lane(r), why: str(r.why) };
}

/** The lanes as the desk reads them; null when the answer is not the lanes view. */
export function parseLanes(raw: unknown): LanesView | null {
  if (!isObject(raw) || typeof raw.schema_version !== 'number') return null;
  return {
    schema_version: raw.schema_version, you: lane(raw.you), claude: lane(raw.claude), brain: brainLane(raw.brain),
    recording_error: str(raw.recording_error),
  };
}

const MODES = ['on', 'off_today', 'off'] as const;
const SOURCES = ['operator', 'env', 'default'] as const;

/** The recording switch (`auto-record-switch.json`); null when it does not parse -- Records then says so. */
export function parseRecordingSwitch(raw: unknown): AutoRecordSwitch | null {
  if (!isObject(raw)) return null;
  const mode = MODES.find(m => m === raw.mode);
  const source = SOURCES.find(s => s === raw.source);
  if (!mode || !source) return null;
  return { mode, source, day: str(raw.day), until: num(raw.until), error: str(raw.error) };
}

/** The lanes on ``symbol`` (two lanes on one stock share its lines). */
export function lanesOn(view: LanesView | null | undefined, symbol: string): LaneOwner[] {
  if (!view) return [];
  const s = symbol.toUpperCase();
  return LANE_OWNERS.filter(o => view[o].symbol === s);
}

/** Who Nova records for: each recorded stock, the lanes on it, and the brain's own words for naming its stock. */
export interface LaneRecording {
  switch: AutoRecordSwitch | null;
  /** The stocks a lane records now, in lane order (yours first). */
  symbols: string[];
  owners: Record<string, LaneOwner[]>;
  /** The brain's words for the stock its lane records, as it wrote them; none for any other stock. */
  why: Record<string, string>;
  error: string | null;
}

export function laneRecording(lanes: LanesView | null | undefined, sw: AutoRecordSwitch | null | undefined): LaneRecording {
  const out: LaneRecording = { switch: sw ?? null, symbols: [], owners: {}, why: {}, error: null };
  if (!lanes) return out;
  out.error = lanes.recording_error;
  for (const owner of LANE_OWNERS) {
    const l = lanes[owner];
    if (!l.symbol || !l.recording) continue;
    if (!out.owners[l.symbol]) out.symbols.push(l.symbol);
    out.owners[l.symbol] = [...(out.owners[l.symbol] ?? []), owner];
  }
  const brain = lanes.brain;
  if (brain.symbol && brain.recording && brain.why) out.why[brain.symbol] = brain.why;
  return out;
}

/** What a waiting pane's poll learned: the lanes, or an answer that could not be read and why. */
export type LanesRead = { kind: 'view'; view: LanesView } | { kind: 'unknown'; error: string };

export async function readLanes(signal?: AbortSignal): Promise<LanesRead> {
  try {
    const res = await novaFetch(`${API_BASE_URL}${LANES_PATH}`, { signal });
    if (!res.ok) return { kind: 'unknown', error: `GET ${LANES_PATH} answered ${res.status}` };
    const view = parseLanes(await res.json());
    return view ? { kind: 'view', view } : { kind: 'unknown', error: `GET ${LANES_PATH}: not the lanes view` };
  } catch (err) {
    return { kind: 'unknown', error: err instanceof Error ? err.message : String(err) };
  }
}
