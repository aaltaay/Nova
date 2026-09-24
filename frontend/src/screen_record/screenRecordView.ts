/**
 * The trading screen recording's status as the desktop app publishes it
 * (electron/screenRecorder.mjs `view()`, ADR 035; shape in AGENTS.md §3).
 * Wire data is checked here once; anything unreadable is null, never a guess.
 */
export type ScreenRecordState = 'starting' | 'recording' | 'partial' | 'failed' | 'suspended' | 'stopped';
export type ScreenDiskState = 'ok' | 'warn' | 'fail' | 'unknown';

export interface ScreenRecordDisplay {
  index: number;
  count: number;
  label: string | null;
  primary: boolean;
  width: number;
  height: number;
  recording: boolean;
  since: number | null;
  file: string | null;
  bytes: number;
  error: string | null;
  retryAt: number | null;
}

export interface ScreenRecordProblem {
  at: number;
  displayIndex: number;
  reason: string;
  detail: string;
  resumedAt: number | null;
}

export interface ScreenRecordView {
  state: ScreenRecordState;
  recording: boolean;
  since: number | null;
  error: string | null;
  dir: string;
  dirSource: 'env' | 'data_drive' | 'fallback';
  dirNote: string | null;
  mime: string | null;
  fps: number;
  segmentMin: number;
  displays: ScreenRecordDisplay[];
  unmatched: number;
  disk: { freeBytes: number | null; state: ScreenDiskState };
  problems: ScreenRecordProblem[];
}

const STATES: readonly ScreenRecordState[] = ['starting', 'recording', 'partial', 'failed', 'suspended', 'stopped'];
const DISK_STATES: readonly ScreenDiskState[] = ['ok', 'warn', 'fail', 'unknown'];
const DIR_SOURCES = ['env', 'data_drive', 'fallback'] as const;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.length ? v : null);

function readDisplay(raw: unknown): ScreenRecordDisplay | null {
  if (!isObj(raw)) return null;
  const index = num(raw.index);
  if (index === null) return null;
  return {
    index,
    count: num(raw.count) ?? 1,
    label: str(raw.label),
    primary: raw.primary === true,
    width: num(raw.width) ?? 0,
    height: num(raw.height) ?? 0,
    recording: raw.recording === true,
    since: num(raw.since),
    file: str(raw.file),
    bytes: num(raw.bytes) ?? 0,
    error: str(raw.error),
    retryAt: num(raw.retry_at),
  };
}

function readProblem(raw: unknown): ScreenRecordProblem | null {
  if (!isObj(raw)) return null;
  const at = num(raw.at);
  const displayIndex = num(raw.display_index);
  if (at === null || displayIndex === null) return null;
  return { at, displayIndex, reason: str(raw.reason) ?? 'error', detail: str(raw.detail) ?? '', resumedAt: num(raw.resumed_at) };
}

export function readScreenRecordView(raw: unknown): ScreenRecordView | null {
  if (!isObj(raw) || raw.schema_version !== 1) return null;
  const state = STATES.find((s) => s === raw.state);
  if (!state) return null;
  const disk = isObj(raw.disk) ? raw.disk : {};
  const dirSource = DIR_SOURCES.find((s) => s === raw.dir_source) ?? 'fallback';
  return {
    state,
    recording: raw.recording === true,
    since: num(raw.since),
    error: str(raw.error),
    dir: str(raw.dir) ?? '',
    dirSource,
    dirNote: str(raw.dir_note),
    mime: str(raw.mime),
    fps: num(raw.fps) ?? 0,
    segmentMin: num(raw.segment_min) ?? 0,
    displays: (Array.isArray(raw.displays) ? raw.displays : []).map(readDisplay).filter((d): d is ScreenRecordDisplay => d !== null),
    unmatched: Array.isArray(raw.unmatched) ? raw.unmatched.length : 0,
    disk: {
      freeBytes: num(disk.free_bytes),
      state: DISK_STATES.find((s) => s === disk.state) ?? 'unknown',
    },
    problems: (Array.isArray(raw.problems) ? raw.problems : []).map(readProblem).filter((p): p is ScreenRecordProblem => p !== null),
  };
}
