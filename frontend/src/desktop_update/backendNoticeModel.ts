/**
 * The backend notice's decisions and words (ADR 038 amendment, 2026-09-29; one version, operator ask
 * 2026-09-30: "i need them to be treated as ONE"). Pure: BackendNotice.tsx reads the tags and the
 * restart check and draws what this returns.
 *
 * The desk and its backend run one release. Restart to update brings both (electron/engineSync.mjs);
 * this notice is for a backend left on another one, with the one action that closes the gap:
 * - behind the desk, running from the operator's checkout: "Update backend to vNNN" -- the checkout
 *   comes to the desk's release and the backend restarts onto it, in one press;
 * - behind, from another checkout that already holds newer code: "Restart backend now";
 * - ahead of the desk (its installer may still be building): "Update desk to vNNN", which looks for
 *   that release now.
 * Before a restart the desk asks the backend what is open (GET /api/diagnostics/restart-check):
 * nothing open goes at once; anything open, or a backend too old to say, is listed and confirmed.
 */
import { backendRemedy, isOlderTag } from '../../electron/appTitle.mjs';
import type { EngineSync } from './updateView';

export const BACKEND_RESTART_CHECK_PATH = '/api/diagnostics/restart-check';
export const BACKEND_NOTICE_RESTART_LABEL = 'Restart backend now';
const RESTART_EFFECT = 'The backend restarts in about half a minute; the desk reconnects by itself.';

export type BackendNoticeAction = 'update' | 'restart' | 'desk';

export type BackendNoticeModel = {
  /** Session "Later" key: the notice comes back when any of the three revisions changes. */
  key: string;
  text: string;
  hint: string;
  action: BackendNoticeAction | null;
  actionLabel: string;
};

type Tags = { backend: string | null; checkout: string | null; desk: string; engine: EngineSync | null };

export function updateBackendLabel(desk: string): string {
  return `Update backend to ${desk}`;
}

export function updateDeskLabel(backend: string): string {
  return `Update desk to ${backend}`;
}

/** The notice for a backend on another release than this desk, or null when they are one. */
export function backendNotice({ backend, checkout, desk, engine }: Tags): BackendNoticeModel | null {
  if (!backend) return null;
  const key = `${backend}|${checkout ?? ''}|${desk}`;
  if (isOlderTag(desk, backend)) {
    return {
      key,
      text: `Backend ${backend} is ahead of this desk (${desk}).`,
      hint: `Nova runs as one version: this looks for the ${backend} desk. Its installer can take a few minutes to build after a merge.`,
      action: 'desk',
      actionLabel: updateDeskLabel(backend),
    };
  }
  const remedy = backendRemedy(backend, desk, checkout);
  if (!remedy) return null;
  const text = `Backend ${backend} is behind this desk (${desk}).`;
  if (engine?.attachedToOwner && engine.owner) {
    return {
      key,
      text,
      hint: `Nova runs as one version: this brings ${engine.owner} to ${desk} and restarts the backend.`,
      action: 'update',
      actionLabel: updateBackendLabel(desk),
    };
  }
  if (remedy === 'restart') {
    return {
      key,
      text,
      hint: checkout ? `Its checkout holds ${checkout}: a restart loads it.` : 'A restart loads what its checkout holds.',
      action: 'restart',
      actionLabel: BACKEND_NOTICE_RESTART_LABEL,
    };
  }
  return {
    key,
    text,
    hint: `It does not run from your Nova checkout: bring its checkout to ${desk}, then restart it (gear, Reload backend).`,
    action: null,
    actionLabel: updateBackendLabel(desk),
  };
}

export type RestartRisk = { safe: boolean | null; lines: string[] };

/** What the restart check says is open. A backend older than the check reads as unknown, never safe. */
export function restartRisk(body: unknown): RestartRisk {
  const raw = body && typeof body === 'object' ? (body as Record<string, unknown>) : null;
  if (!raw || raw.schema_version !== 1) {
    return { safe: null, lines: ['The backend did not say what is open (it may be older than the check): check your positions and recordings.'] };
  }
  const text = (row: unknown) => {
    const t = row && typeof row === 'object' ? (row as Record<string, unknown>).text : null;
    return typeof t === 'string' && t ? t : null;
  };
  const open = Array.isArray(raw.open) ? raw.open.map(text).filter((t): t is string => t !== null) : [];
  const unknown = Array.isArray(raw.unknown)
    ? raw.unknown.map((row) => {
        const r = row && typeof row === 'object' ? (row as Record<string, unknown>) : {};
        return `Could not read ${String(r.kind ?? 'something')}: ${String(r.error ?? 'unknown error')}`;
      })
    : [];
  const safe = raw.safe === true ? true : raw.safe === false ? false : null;
  return { safe, lines: [...open, ...unknown] };
}

/** Nothing open goes in one click; anything open, or a backend that cannot say, is confirmed. */
export function needsConfirm(action: BackendNoticeAction, risk: RestartRisk): boolean {
  return action !== 'desk' && risk.safe !== true;
}

/** The confirmation: what the action does, then what is open. */
export function confirmText(action: BackendNoticeAction, risk: RestartRisk, owner: string | null, desk: string): string {
  const what = action === 'update'
    ? `Brings ${owner ?? "the backend's checkout"} to ${desk} (fast-forward only), then restarts the backend. `
      + 'A browser desk on port 5173 reloads with the new code.'
    : 'Restarts the backend onto the code its checkout holds.';
  const open = risk.safe === true
    ? 'Nothing is open.'
    : `Open now:\n${risk.lines.map((line) => `- ${line}`).join('\n')}`;
  return `${what} ${RESTART_EFFECT}\n\n${open}`;
}
