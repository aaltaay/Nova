/**
 * What's new: the release notes of the update the operator just installed,
 * shown on the desk the first time a new version opens (operator ask,
 * 2026-09-23), and again on request from Help > What's New.
 *
 * Persisted state: `<userData>/whats-new.json`, `schema_version` 1:
 * `{schema_version, seen_tag, closed_at}` -- the release whose notes the operator
 * last closed. Owner: this module. Invalidation: closing the card writes the
 * installed tag. No file (a fresh install, or the first version with What's new)
 * shows the installed release's own notes. An unknown schema_version is left
 * alone and shows nothing.
 */
import fs from 'node:fs';
import path from 'node:path';
import { RECENT_RELEASES_LISTED, notesText, whatsNewRange } from './releaseNotes.mjs';
import { LOADING_NOTES } from './releaseNotesSource.mjs';

export const WHATS_NEW_FILE = 'whats-new.json';
export const WHATS_NEW_SCHEMA_VERSION = 1;

/**
 * @param {{ bridge: ReturnType<typeof import('./updateBridge.mjs').createUpdateBridge>,
 *   notesSource: { load: (range: object) => Promise<any> }, dir: () => string,
 *   installedTag: string, logger: { info: Function, warn: Function },
 *   showDialog: (options: object) => Promise<unknown>, now?: () => Date }} deps
 */
export function createWhatsNew({ bridge, notesSource, dir, installedTag, logger, showDialog, now = () => new Date() }) {
  let shown = 0;
  const file = () => {
    const folder = dir();
    return folder ? path.join(folder, WHATS_NEW_FILE) : '';
  };

  /** `{ ok: true, seen }` (seen null when never closed), or `{ ok: false }` for a file this version does not read. */
  function readSeen() {
    const target = file();
    if (!target || !fs.existsSync(target)) return { ok: true, seen: null };
    try {
      const parsed = JSON.parse(fs.readFileSync(target, 'utf8'));
      if (parsed?.schema_version !== WHATS_NEW_SCHEMA_VERSION) {
        logger.warn(`${target} has schema_version ${parsed?.schema_version}; What's new stays closed`);
        return { ok: false };
      }
      return { ok: true, seen: typeof parsed.seen_tag === 'string' ? parsed.seen_tag : null };
    } catch (err) {
      logger.warn(`${target} unreadable (${err instanceof Error ? err.message : String(err)}); showing this release's notes`);
      return { ok: true, seen: null };
    }
  }

  function writeSeen() {
    const target = file();
    if (!target) return;
    const body = { schema_version: WHATS_NEW_SCHEMA_VERSION, seen_tag: installedTag, closed_at: now().toISOString() };
    try {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(`${target}.tmp`, JSON.stringify(body));
      fs.renameSync(`${target}.tmp`, target);
    } catch (err) {
      logger.warn(`What's new not recorded as read: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function show(mode, range) {
    shown += 1;
    const ticket = shown;
    const card = { mode, tag: installedTag, since: range.since ?? null };
    bridge.set('whats_new', { ...card, notes: LOADING_NOTES });
    const notes = await notesSource.load(range);
    // Closed (or replaced) while the notes loaded: leave it closed.
    if (ticket === shown) bridge.set('whats_new', { ...card, notes });
    return notes;
  }

  return {
    /** On launch: the card for an update the operator has not read yet. */
    async start() {
      const seen = readSeen();
      if (!seen.ok) return;
      const range = whatsNewRange({ installed: installedTag, seen: seen.seen });
      if (!range) return;
      logger.info(`What's new: ${installedTag}${range.since ? ` since ${range.since}` : ''}`);
      await show('updated', range);
    },

    /** Help > What's New: the installed release and the ones before it, on the desk or in a dialog. */
    async openRecent() {
      const range = { after: null, through: installedTag, limit: RECENT_RELEASES_LISTED, since: null };
      if (bridge.hasListener()) {
        await show('recent', range);
        return;
      }
      const notes = await notesSource.load(range);
      await showDialog({
        type: 'info',
        title: `What's new in Nova ${installedTag}`,
        message: `What's new in Nova ${installedTag}`,
        detail: notes.error || notesText(notes.releases) || 'No release notes were recorded for this version.',
        buttons: ['OK'],
        noLink: true,
      });
    },

    /** The operator closed the card: it is not shown again for this version. */
    close() {
      shown += 1;
      bridge.set('whats_new', null);
      writeSeen();
    },
  };
}
