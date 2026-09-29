/**
 * The backend notice's decisions and words (ADR 038 amendment, 2026-09-29). Pure: BackendNotice.tsx
 * reads the tags and the restart check and draws what this returns.
 *
 * A backend older than the desk (the window title's "(older -- ...)") gets a notice in the update
 * strip with the one action that helps: "Restart backend now" when its checkout already holds newer
 * code, "Pull master and restart" when the checkout holds nothing newer and the desk can pull it
 * (electron/engineSync.mjs). Before either, the desk asks the backend what is open
 * (GET /api/diagnostics/restart-check): nothing open restarts at once; anything open, or a backend
 * too old to say, is listed and confirmed first. A pull is always confirmed.
 */
import { backendRemedy } from '../../electron/appTitle.mjs';
import type { EngineSync } from './updateView';

export const BACKEND_RESTART_CHECK_PATH = '/api/diagnostics/restart-check';
export const BACKEND_NOTICE_RESTART_LABEL = 'Restart backend now';
export const BACKEND_NOTICE_SYNC_LABEL = 'Pull master and restart';
const RESTART_EFFECT = 'The backend restarts in about half a minute; the desk reconnects by itself.';

export type BackendNoticeAction = 'restart' | 'sync';

export type BackendNoticeModel = {
  /** Session "Later" key: the notice comes back when any of the three revisions changes. */
  key: string;
  text: string;
  hint: string;
  action: BackendNoticeAction | null;
  actionLabel: string;
};

type Tags = { backend: string | null; checkout: string | null; desk: string; engine: EngineSync | null };

/** The notice for a backend older than this desk, or null when there is nothing to say. */
export function backendNotice({ backend, checkout, desk, engine }: Tags): BackendNoticeModel | null {
  const remedy = backend ? backendRemedy(backend, desk, checkout) : null;
  if (!backend || !remedy) return null;
  const key = `${backend}|${checkout ?? ''}|${desk}`;
  if (remedy === 'restart') {
    return {
      key,
      text: `Backend ${backend} runs older code than this desk (${desk}).`,
      hint: checkout ? `Its checkout holds ${checkout}: a restart loads it.` : 'A restart loads what its checkout holds.',
      action: 'restart',
      actionLabel: BACKEND_NOTICE_RESTART_LABEL,
    };
  }
  const canPull = Boolean(engine?.attachedToOwner && engine.owner);
  return {
    key,
    text: `Backend ${backend} runs older code than this desk (${desk}), and its checkout holds nothing newer.`,
    hint: canPull
      ? `${BACKEND_NOTICE_SYNC_LABEL} brings ${engine?.owner} to master.`
      : 'Pull master in its checkout, then restart it (gear, Reload backend).',
    action: canPull ? 'sync' : null,
    actionLabel: BACKEND_NOTICE_SYNC_LABEL,
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

/** One click restarts only when the backend said nothing is open; a pull is always confirmed. */
export function needsConfirm(action: BackendNoticeAction, risk: RestartRisk): boolean {
  return action === 'sync' || risk.safe !== true;
}

/** The confirmation: what the action does, then what is open. */
export function confirmText(action: BackendNoticeAction, risk: RestartRisk, owner: string | null): string {
  const what = action === 'sync'
    ? `Pulls master into ${owner ?? 'the backend\'s checkout'} (fast-forward only), then restarts the backend. `
      + 'A browser desk on port 5173 reloads with the new code.'
    : 'Restarts the backend onto the code its checkout holds.';
  const open = risk.safe === true
    ? 'Nothing is open.'
    : `Open now:\n${risk.lines.map((line) => `- ${line}`).join('\n')}`;
  return `${what} ${RESTART_EFFECT}\n\n${open}`;
}
