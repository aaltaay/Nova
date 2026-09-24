/**
 * How the in-app updater reaches the operator (operator ask, 2026-09-23): the
 * notice it publishes to the desk (updateBridge.mjs) with the release notes of
 * the version on offer, the Help menu's update rows, the dialogs it falls back
 * to when the window cannot show the notice, and the taskbar flash that points
 * at them. What to say is updateCopy.mjs; when to say it is updatePolicy.mjs.
 */
import { dialog, Menu } from 'electron';
import { LOADING_NOTES } from './releaseNotesSource.mjs';
import { errorText, noticeFor } from './updatePolicy.mjs';

/**
 * @param {{ bridge: { set: Function, hasListener: () => boolean },
 *   notesSource: { load: (range: object) => Promise<any> } | null,
 *   getWindow: () => any, getState: () => any, installedTag: () => string,
 *   logger: { error: Function } }} deps
 */
export function createUpdateAsk({ bridge, notesSource, getWindow, getState, installedTag, logger }) {
  // The release notes of the version on offer: everything after the installed release up to it.
  let offerNotes = { tag: '', notes: null, promise: null };
  let lastMenuKey = '';

  /** Push the notice for the updater's current state, with the notes of its version. */
  function publish() {
    const notice = noticeFor(getState());
    const notes = notice && offerNotes.tag === notice.tag ? offerNotes.notes : null;
    bridge.set('notice', notice && { ...notice, installed: installedTag(), notes });
  }

  /** Load `tag`'s notes once per session (a failed load is tried again), publishing as they arrive. */
  function notesFor(tag) {
    if (offerNotes.tag === tag && offerNotes.promise && !offerNotes.notes?.error) return offerNotes.promise;
    const promise = notesSource
      ? notesSource.load({ after: installedTag(), through: tag })
      : Promise.resolve({ ...LOADING_NOTES, loading: false, error: 'Release notes are unavailable.' });
    offerNotes = { tag, notes: LOADING_NOTES, promise };
    publish();
    void promise.then((notes) => {
      if (offerNotes.tag !== tag) return;
      offerNotes = { ...offerNotes, notes };
      publish();
    });
    return promise;
  }

  function liveWindow() {
    const win = getWindow();
    return win && !win.isDestroyed() ? win : null;
  }

  /** A dialog over the desk (answers to a Help-menu request). */
  async function box(options) {
    try {
      const win = liveWindow();
      return win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
    } catch (err) {
      logger.error(`dialog failed: ${errorText(err)}`);
      return { response: -1 };
    }
  }

  /** A question with no parent window, so it never blocks the trading window it sits over. */
  async function ask(options) {
    const win = liveWindow();
    if (win) win.flashFrame(true);
    let response = -1;
    try {
      ({ response } = await dialog.showMessageBox(options));
    } catch (err) {
      logger.error(`update prompt failed: ${errorText(err)}`);
    }
    if (win && !win.isDestroyed()) win.flashFrame(false);
    return response;
  }

  /** Flash the taskbar button until the operator comes back to the desk. */
  function attention() {
    const win = liveWindow();
    if (!win || win.isFocused?.()) return;
    win.flashFrame(true);
    win.once?.('focus', () => {
      if (!win.isDestroyed()) win.flashFrame(false);
    });
  }

  /**
   * The application menu with `rows` (updateCopy.updateMenuItems) under Help;
   * `clicks` maps a row's action to what it does. Rebuilt only when a row changes.
   */
  function setMenu(rows, clicks) {
    const key = JSON.stringify(rows);
    if (key === lastMenuKey) return;
    lastMenuKey = key;
    const submenu = rows.map((row) => ({ label: row.label, enabled: Boolean(row.action), click: clicks[row.action] }));
    // Same roles as Electron's default Windows menu; only Help gains the update rows.
    const template = [
      { role: 'fileMenu' },
      { role: 'editMenu' },
      { role: 'viewMenu' },
      { role: 'windowMenu' },
      { role: 'help', submenu },
    ];
    try {
      Menu.setApplicationMenu(Menu.buildFromTemplate(template));
    } catch (err) {
      logger.error(`menu update failed: ${errorText(err)}`);
    }
  }

  return { publish, notesFor, box, ask, attention, setMenu };
}
