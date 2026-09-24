/**
 * The update view the Electron main process publishes (electron/updateBridge.mjs;
 * schema in AGENTS.md §3), and the one shape gate every frame passes through.
 * A frame of another schema version, or a part that does not parse, reads as
 * absent -- the desk shows nothing rather than a half-read notice.
 */

export const UPDATE_VIEW_SCHEMA_VERSION = 1;

export type ReleaseNote = {
  tag: string;
  /** False for a release made before release notes existed: it has a tag and nothing else. */
  recorded: boolean;
  title: string;
  kind: string | null;
  scope: string | null;
  pr: number | null;
  prUrl: string | null;
  summary: string;
  points: string[];
  url: string;
};

export type ReleaseNotes = {
  loading: boolean;
  error: string | null;
  releases: ReleaseNote[];
  /** Releases in range past the listed ones. */
  more: number;
  /** GitHub holds releases in range the one page fetched did not reach. */
  olderUnlisted: boolean;
  pageUrl: string;
};

export type NoticeStage = 'available' | 'downloading' | 'stopped' | 'ready' | 'installing';

export type UpdateNotice = {
  stage: NoticeStage;
  tag: string;
  installed: string;
  percent: number;
  retry: number;
  error: string;
  notes: ReleaseNotes | null;
};

export type WhatsNew = {
  /** `updated`: the first launch after an update; `recent`: Help > What's New. */
  mode: 'updated' | 'recent';
  tag: string;
  since: string | null;
  notes: ReleaseNotes;
};

export type UpdateView = {
  installed: string;
  notice: UpdateNotice | null;
  whatsNew: WhatsNew | null;
  /** Help > File an Issue…: when the operator last asked (ms); a new value opens the issue form. */
  fileIssueRequestedAt: number | null;
};

/** What the operator can answer (electron/autoUpdate.mjs wireBridge). */
export type UpdateAction = 'download' | 'later' | 'restart' | 'whats-new-close' | 'open-link';

const STAGES: readonly NoticeStage[] = ['available', 'downloading', 'stopped', 'ready', 'installing'];

type Raw = Record<string, unknown>;

function obj(value: unknown): Raw | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Raw) : null;
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function strOrNull(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}

function count(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

function readNote(value: unknown): ReleaseNote | null {
  const raw = obj(value);
  const tag = str(raw?.tag);
  if (!raw || !/^v\d+$/.test(tag)) return null;
  const pr = Number(raw.pr);
  return {
    tag,
    recorded: raw.recorded === true,
    title: str(raw.title),
    kind: strOrNull(raw.kind),
    scope: strOrNull(raw.scope),
    pr: Number.isInteger(pr) && pr > 0 ? pr : null,
    prUrl: strOrNull(raw.pr_url),
    summary: str(raw.summary),
    points: Array.isArray(raw.points) ? raw.points.filter((p): p is string => typeof p === 'string' && p !== '') : [],
    url: str(raw.url),
  };
}

export function readReleaseNotes(value: unknown): ReleaseNotes | null {
  const raw = obj(value);
  if (!raw) return null;
  const releases = Array.isArray(raw.releases)
    ? raw.releases.map(readNote).filter((n): n is ReleaseNote => n !== null)
    : [];
  return {
    loading: raw.loading === true,
    error: strOrNull(raw.error),
    releases,
    more: count(raw.more),
    olderUnlisted: raw.older_unlisted === true,
    pageUrl: str(raw.page_url),
  };
}

function readNotice(value: unknown): UpdateNotice | null {
  const raw = obj(value);
  const stage = str(raw?.stage) as NoticeStage;
  if (!raw || !STAGES.includes(stage) || !str(raw.tag)) return null;
  return {
    stage,
    tag: str(raw.tag),
    installed: str(raw.installed),
    percent: Math.min(100, count(raw.percent)),
    retry: count(raw.retry),
    error: str(raw.error),
    notes: readReleaseNotes(raw.notes),
  };
}

function readWhatsNew(value: unknown): WhatsNew | null {
  const raw = obj(value);
  const notes = readReleaseNotes(raw?.notes);
  if (!raw || !notes || !str(raw.tag)) return null;
  return {
    mode: raw.mode === 'recent' ? 'recent' : 'updated',
    tag: str(raw.tag),
    since: strOrNull(raw.since),
    notes,
  };
}

/** One frame from the main process, or null when it is not a view this desk reads. */
export function readUpdateView(value: unknown): UpdateView | null {
  const raw = obj(value);
  if (!raw || raw.schema_version !== UPDATE_VIEW_SCHEMA_VERSION) return null;
  return {
    installed: str(raw.installed),
    notice: readNotice(raw.notice),
    whatsNew: readWhatsNew(raw.whats_new),
    fileIssueRequestedAt: count(obj(raw.file_issue)?.requested_at) || null,
  };
}

const KIND_LABELS: Record<string, string> = {
  feat: 'New',
  fix: 'Fix',
  perf: 'Faster',
  refactor: 'Internal',
  chore: 'Maintenance',
  docs: 'Docs',
  build: 'Build',
  ci: 'Build',
  test: 'Tests',
  revert: 'Revert',
};

/** `feat` -> `New`; an unknown kind is shown as written. */
export function kindLabel(kind: string | null): string {
  if (!kind) return '';
  return KIND_LABELS[kind] ?? kind;
}
