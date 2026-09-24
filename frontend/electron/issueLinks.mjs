/**
 * Help > File an Issue… and the links the desk's issue form opens (operator ask, 2026-09-24).
 *
 * The form itself is the renderer's (frontend/src/issue_report/); the backend files the issue
 * (backend/issue_report/). This module decides where the menu's request goes -- the desk's form
 * when the main window's page is listening, else GitHub's new-issue page in the browser -- and
 * which links the form may ask the main process to open: this repository's issues (a filed one,
 * or the prefilled new-issue page) and a gist (the uploaded dump).
 */
import { RELEASES_REPO } from './releaseNotes.mjs';

export const ISSUES_REPO = RELEASES_REPO;
export const NEW_ISSUE_PAGE = `https://github.com/${ISSUES_REPO}/issues/new/choose`;

const ISSUE_PATH = new RegExp(`^/${ISSUES_REPO}/issues/(?:\\d+|new(?:/choose)?)/?$`);
const GIST_PATH = /^\/[A-Za-z0-9-]{1,39}\/[0-9a-f]{20,40}\/?$/;

/** A link the issue form may open: this repository's issue pages, or a gist. */
export function isIssueLink(url) {
  let parsed;
  try {
    parsed = new URL(String(url ?? ''));
  } catch {
    return false;
  }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port) return false;
  if (parsed.hostname === 'github.com') return ISSUE_PATH.test(parsed.pathname);
  if (parsed.hostname === 'gist.github.com') return GIST_PATH.test(parsed.pathname) && !parsed.search;
  return false;
}

/**
 * The Help-menu action. Opens the desk's form (a new `file_issue.requested_at` in the update
 * view, and the main window brought forward); with no page listening, GitHub's page instead.
 * @param {{ bridge: { hasListener: () => boolean, set: (part: string, value: unknown) => void },
 *   getWindow: () => any, openExternal: (url: string) => Promise<unknown>, now?: () => number,
 *   logger: { warn: Function } }} deps
 */
export function createIssueRequest({ bridge, getWindow, openExternal, now = Date.now, logger }) {
  return function requestIssueForm() {
    if (bridge.hasListener()) {
      bridge.set('file_issue', { requested_at: now() });
      const win = getWindow();
      if (win && !win.isDestroyed()) {
        if (win.isMinimized()) win.restore();
        win.focus();
      }
      return 'desk';
    }
    Promise.resolve(openExternal(NEW_ISSUE_PAGE)).catch((err) =>
      logger.warn(`could not open ${NEW_ISSUE_PAGE}: ${err instanceof Error ? err.message : String(err)}`),
    );
    return 'browser';
  };
}
