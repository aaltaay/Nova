/**
 * Share clips' view as the desktop app publishes it (electron/clipService.mjs
 * `view()`, ADR 039; shape in AGENTS.md §3 "Share clips"). Wire data is
 * checked here once; anything unreadable is null or left out, never a guess.
 */
export type ClipOpenState = 'ok' | 'hidden' | 'hq_lost' | 'no_picture';
export type ClipStatus = 'recording' | 'not_exported' | 'queued' | 'exporting' | 'ready' | 'failed' | 'cancelled';
export type ClipDiskState = 'ok' | 'warn' | 'fail' | 'unknown';

export interface OpenClipHq {
  since: number | null;
  endsAt: number | null;
  recording: boolean;
  lost: boolean;
  error: string | null;
  retryAt: number | null;
}

export interface OpenClip {
  clipId: string;
  symbol: string;
  startedTs: number;
  state: ClipOpenState;
  reason: string | null;
  showing: string | null;
  windowId: string | null;
  screenRecording: boolean | null;
  hq: OpenClipHq | null;
}

export interface ClipExportView {
  exportId: string;
  state: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  file: string | null;
  bytes: number | null;
  error: string | null;
  progress: number | null;
  picture: string | null;
  blur: string[];
}

export interface ClipRowView {
  clipId: string;
  symbol: string;
  origin: string;
  picture: string;
  startedTs: number;
  endedTs: number | null;
  lengthSec: number;
  status: ClipStatus;
  hqSec: number;
  hiddenSec: number;
  gapSec: number;
  export: ClipExportView | null;
}

export interface ClipTabView {
  windowId: string;
  symbol: string | null;
  visible: boolean;
  displayId: string | null;
  screenRecording: boolean | null;
}

export interface ClipsView {
  generatedAt: number;
  dir: string;
  dirSource: 'env' | 'data_drive' | 'fallback';
  dirNote: string | null;
  dirError: string | null;
  hqMax: number;
  hqInUse: number;
  hqMaxSec: number;
  hqWarnSec: number;
  lastNSec: number;
  open: OpenClip[];
  clips: ClipRowView[];
  exporting: { exportId: string; clipId: string; doneSec: number; duration: number } | null;
  queued: number;
  tabs: ClipTabView[];
  disk: { freeBytes: number | null; state: ClipDiskState };
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.length ? v : null);
const oneOf = <T extends string>(v: unknown, list: readonly T[]): T | null => (list.find((x) => x === v) ?? null);
const list = <T>(v: unknown, read: (x: unknown) => T | null): T[] =>
  (Array.isArray(v) ? v : []).map(read).filter((x): x is T => x !== null);

const OPEN_STATES = ['ok', 'hidden', 'hq_lost', 'no_picture'] as const;
const STATUSES = ['recording', 'not_exported', 'queued', 'exporting', 'ready', 'failed', 'cancelled'] as const;
const EXPORT_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'] as const;
const DISK = ['ok', 'warn', 'fail', 'unknown'] as const;

function readOpen(raw: unknown): OpenClip | null {
  if (!isObj(raw)) return null;
  const clipId = str(raw.clip_id);
  const symbol = str(raw.symbol);
  const startedTs = num(raw.started_ts);
  if (!clipId || !symbol || startedTs === null) return null;
  const hq = isObj(raw.hq)
    ? {
        since: num(raw.hq.since),
        endsAt: num(raw.hq.ends_at),
        recording: raw.hq.recording === true,
        lost: raw.hq.lost === true,
        error: str(raw.hq.error),
        retryAt: num(raw.hq.retry_at),
      }
    : null;
  return {
    clipId,
    symbol,
    startedTs,
    state: oneOf(raw.state, OPEN_STATES) ?? 'ok',
    reason: str(raw.reason),
    showing: str(raw.showing),
    windowId: str(raw.window_id),
    screenRecording: typeof raw.screen_recording === 'boolean' ? raw.screen_recording : null,
    hq,
  };
}

function readExport(raw: unknown): ClipExportView | null {
  if (!isObj(raw)) return null;
  const exportId = str(raw.export_id);
  const state = oneOf(raw.state, EXPORT_STATES);
  if (!exportId || !state) return null;
  return {
    exportId,
    state,
    file: str(raw.file),
    bytes: num(raw.bytes),
    error: str(raw.error),
    progress: num(raw.progress),
    picture: str(raw.picture),
    blur: list(raw.blur, (x) => str(x)),
  };
}

function readRow(raw: unknown): ClipRowView | null {
  if (!isObj(raw)) return null;
  const clipId = str(raw.clip_id);
  const symbol = str(raw.symbol);
  const startedTs = num(raw.started_ts);
  const status = oneOf(raw.status, STATUSES);
  if (!clipId || !symbol || startedTs === null || !status) return null;
  return {
    clipId,
    symbol,
    origin: str(raw.origin) ?? 'button',
    picture: str(raw.picture) ?? 'trader_tab',
    startedTs,
    endedTs: num(raw.ended_ts),
    lengthSec: num(raw.length_sec) ?? 0,
    status,
    hqSec: num(raw.hq_sec) ?? 0,
    hiddenSec: num(raw.hidden_sec) ?? 0,
    gapSec: num(raw.gap_sec) ?? 0,
    export: readExport(raw.export),
  };
}

function readTab(raw: unknown): ClipTabView | null {
  if (!isObj(raw)) return null;
  const windowId = str(raw.window_id);
  if (!windowId) return null;
  return {
    windowId,
    symbol: str(raw.symbol),
    visible: raw.visible === true,
    displayId: str(raw.display_id),
    screenRecording: typeof raw.screen_recording === 'boolean' ? raw.screen_recording : null,
  };
}

export function readClipsView(raw: unknown): ClipsView | null {
  if (!isObj(raw) || raw.schema_version !== 1) return null;
  const disk = isObj(raw.disk) ? raw.disk : {};
  const ex = isObj(raw.exporting) ? raw.exporting : null;
  return {
    generatedAt: num(raw.generated_at) ?? 0,
    dir: str(raw.dir) ?? '',
    dirSource: oneOf(raw.dir_source, ['env', 'data_drive', 'fallback'] as const) ?? 'fallback',
    dirNote: str(raw.dir_note),
    dirError: str(raw.dir_error),
    hqMax: num(raw.hq_max) ?? 2,
    hqInUse: num(raw.hq_in_use) ?? 0,
    hqMaxSec: num(raw.hq_max_sec) ?? 1800,
    hqWarnSec: num(raw.hq_warn_sec) ?? 60,
    lastNSec: num(raw.last_n_sec) ?? 300,
    open: list(raw.open, readOpen),
    clips: list(raw.clips, readRow),
    exporting: ex && str(ex.export_id) && str(ex.clip_id)
      ? { exportId: String(ex.export_id), clipId: String(ex.clip_id), doneSec: num(ex.done_sec) ?? 0, duration: num(ex.duration) ?? 0 }
      : null,
    queued: num(raw.queued) ?? 0,
    tabs: list(raw.tabs, readTab),
    disk: { freeBytes: num(disk.free_bytes), state: oneOf(disk.state, DISK) ?? 'unknown' },
  };
}
