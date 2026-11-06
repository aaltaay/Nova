/**
 * What a held development page knows about its own code and the code on disk
 * (#612; architecture/schema/desk-ops.md, "The browser development desk holds
 * new code"). Pure: no DOM, no timers.
 *
 * The page's revision is the one its HTML was served with (the
 * `nova-dev-code` meta, `<boot>.<seq>`); the dev server announces the disk's
 * (`nova:dev-code`, `CodeState`). Different means pending. Nothing here ever
 * applies the pending code -- only the operator's Reload does.
 */

/** Mirrors `frontend/scripts/vite-nova-reload-hold.ts` (the server half). */
export const CODE_EVENT = 'nova:dev-code';
export const HELLO_EVENT = 'nova:dev-code:hello';
export const CODE_META = 'nova-dev-code';

export type CodeChangeKind = 'source' | 'html' | 'config' | 'reload';

export interface CodeChange {
  seq: number;
  kind: CodeChangeKind;
  file: string | null;
}

export interface CodeState {
  schema_version: 1;
  boot: string;
  seq: number;
  head: string | null;
  at: string;
  recent: CodeChange[];
}

export interface RunningCode {
  boot: string;
  seq: number;
  head: string | null;
}

/** `up` while the dev server's socket is open; `down` once it closed; `back` once it answers again. */
export type ServerLink = 'up' | 'down' | 'back';

export interface HoldView {
  running: RunningCode;
  /** The newest code the dev server announced, or read from its HTML once it came back. */
  disk: CodeState | null;
  server: ServerLink;
  /** The page's own guard caught a Vite update or reload the server did not hold. */
  heldUpdate: boolean;
  /** Later: the notice is folded into its chip. */
  folded: boolean;
}

/** `content="<boot>.<seq>"`; null when it is not one (no hold on this page). */
export function parseRunning(content: string | null | undefined, head: string | null | undefined): RunningCode | null {
  const m = /^([0-9a-z]+)\.(\d+)$/.exec((content ?? '').trim());
  if (!m) return null;
  const h = (head ?? '').trim();
  return { boot: m[1], seq: Number(m[2]), head: h || null };
}

/** The code the page's own HTML was served with, or null when the dev server does not hold. */
export function readRunningCode(doc: Pick<Document, 'querySelector'>): RunningCode | null {
  const meta = doc.querySelector(`meta[name="${CODE_META}"]`);
  if (!meta) return null;
  return parseRunning(meta.getAttribute('content'), meta.getAttribute('data-head'));
}

/** The same meta read from a fetched HTML page (the dev server once it is back). */
export function runningFromHtml(html: string): RunningCode | null {
  const tag = new RegExp(`<meta[^>]*name="${CODE_META}"[^>]*>`).exec(html)?.[0];
  if (!tag) return null;
  const content = /content="([^"]*)"/.exec(tag)?.[1];
  const head = /data-head="([^"]*)"/.exec(tag)?.[1];
  return parseRunning(content, head);
}

function isCodeState(data: unknown): data is CodeState {
  if (!data || typeof data !== 'object') return false;
  const d = data as Partial<CodeState>;
  return d.schema_version === 1 && typeof d.boot === 'string' && typeof d.seq === 'number' && Array.isArray(d.recent);
}

export function initialView(running: RunningCode): HoldView {
  return { running, disk: null, server: 'up', heldUpdate: false, folded: false };
}

/** A `nova:dev-code` announcement. Any other shape is ignored. */
export function withServerCode(view: HoldView, data: unknown): HoldView {
  if (!isCodeState(data)) return view;
  return { ...view, disk: data };
}

/** The socket closed, or a later check found the dev server down again. Only the first stop unfolds Later. */
export function withDisconnect(view: HoldView): HoldView {
  if (view.server === 'down') return view;
  return { ...view, server: 'down', folded: view.server === 'up' ? false : view.folded };
}

/** The dev server answers again; `code` is what its HTML says it serves now (null when unread). */
export function withServerBack(view: HoldView, code: RunningCode | null): HoldView {
  const disk: CodeState | null = code
    ? { schema_version: 1, boot: code.boot, seq: code.seq, head: code.head, at: '', recent: [] }
    : view.disk;
  if (view.server === 'back' && sameCode(view.disk, disk)) return view;
  return { ...view, server: 'back', disk };
}

function sameCode(a: CodeState | null, b: CodeState | null): boolean {
  return a === b || (!!a && !!b && a.boot === b.boot && a.seq === b.seq && a.head === b.head);
}

export function withHeldUpdate(view: HoldView): HoldView {
  return view.heldUpdate ? view : { ...view, heldUpdate: true, folded: false };
}

export function withFolded(view: HoldView, folded: boolean): HoldView {
  return view.folded === folded ? view : { ...view, folded };
}

export interface PendingSummary {
  /** Held changes since this page loaded; null when the dev server restarted (it counts afresh). */
  changes: number | null;
  restarted: boolean;
  server: ServerLink;
  /** Up to three changed files, newest first. */
  files: string[];
  moreFiles: number;
  runningHead: string | null;
  diskHead: string | null;
}

export const LISTED_FILES = 3;

/** What the notice says, or null when this page runs the code on disk. */
export function pendingSummary(view: HoldView): PendingSummary | null {
  const { running, disk, server, heldUpdate } = view;
  const restarted = server !== 'up' || (disk !== null && disk.boot !== running.boot);
  const newer = disk !== null && (disk.boot !== running.boot || disk.seq !== running.seq);
  if (!newer && !restarted && !heldUpdate) return null;
  const sameBoot = disk !== null && disk.boot === running.boot;
  const changes = sameBoot ? disk.recent.filter((c) => c.seq > running.seq) : (disk?.recent ?? []);
  const files = [...new Set(changes.map((c) => c.file).filter((f): f is string => !!f))];
  return {
    changes: sameBoot && !restarted ? Math.max(disk.seq - running.seq, 0) : null,
    restarted,
    server,
    files: files.slice(0, LISTED_FILES),
    moreFiles: Math.max(files.length - LISTED_FILES, 0),
    runningHead: running.head,
    diskHead: disk?.head ?? null,
  };
}
