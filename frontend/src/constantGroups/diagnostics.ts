/**
 * Desk diagnostics checklist (ADR 021) -- labels and tunables for the panel
 * that renders `GET /api/diagnostics` inside the Trading prerequisites gate.
 */

/** How often the open checklist re-reads the API. */
export const DIAG_POLL_MS = 5_000;
export const DIAG_PATH = '/api/diagnostics';
export const DIAG_BUNDLE_PATH = '/api/diagnostics/bundle';

export const DIAG_TITLE = 'Desk diagnostics';
export const DIAG_LEAD =
  'What this API process sees right now, fact by fact. Expand a row for its cause, the fix and the raw evidence.';
export const DIAG_COPY_LABEL = 'Copy diagnostics';
export const DIAG_COPIED_LABEL = 'Copied';
export const DIAG_COPY_FAILED = 'Copy failed -- select the text below';
export const DIAG_REFRESH_LABEL = 'Refresh';
export const DIAG_UNREACHABLE =
  'The API did not answer /api/diagnostics -- the checks below come from the desk itself.';
export const DIAG_CAUSE_LABEL = 'Cause';
export const DIAG_FIX_LABEL = 'Fix';
export const DIAG_EVIDENCE_LABEL = 'Evidence';
export const DIAG_SINCE_LABEL = 'since';

export const DIAG_STATE_LABELS: Record<string, string> = {
  ok: 'OK',
  warn: 'Warn',
  fail: 'Fail',
  off: 'Off',
  unknown: 'Unknown',
};

export const DIAG_COUNTS_ORDER = ['fail', 'warn', 'unknown', 'off', 'ok'] as const;

/** Why a row's action is locked while that action runs (ux/whyTip.ts). */
export const DIAG_WHY_RELOADING = 'Restarting the Nova API -- this unlocks when it answers.';
export const diagActionRunningWhy = (label: string): string =>
  `${label} is already running -- this unlocks when it finishes.`;
