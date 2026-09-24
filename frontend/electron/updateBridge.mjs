/**
 * The update notice and the What's new card, between the main process and the
 * desk window (operator ask, 2026-09-23).
 *
 * The main process owns the facts -- the updater's state (updatePolicy.mjs) and
 * the release notes (releaseNotesSource.mjs) -- and publishes them as one view;
 * the main window's renderer (frontend/src/desktop_update/) draws it and sends
 * back the operator's choices. Only the main window: a Trader pop-out neither
 * receives the view nor may act on it. View schema: AGENTS.md §3.
 *
 * A window counts as listening from its subscribe until it navigates or its
 * renderer dies, so a desk showing an error page gets the native dialogs instead.
 */
export const UPDATE_VIEW_CHANNEL = 'nova:update:view';
export const UPDATE_SUBSCRIBE_CHANNEL = 'nova:update:subscribe';
export const UPDATE_ACT_CHANNEL = 'nova:update:act';
export const UPDATE_VIEW_SCHEMA_VERSION = 1;

export const EMPTY_UPDATE_VIEW = Object.freeze({
  schema_version: UPDATE_VIEW_SCHEMA_VERSION,
  installed: '',
  notice: null,
  whats_new: null,
});

function errorLine(err) {
  return err instanceof Error ? err.message : String(err ?? 'unknown error');
}

/**
 * @param {{ ipcMain: { handle: Function }, getWindow: () => any,
 *   logger: { info: Function, warn: Function, error: Function } }} deps
 */
export function createUpdateBridge({ ipcMain, getWindow, logger }) {
  let view = EMPTY_UPDATE_VIEW;
  let lastSent = '';
  let listener = null;
  const watched = new WeakSet();
  const handlers = new Map();

  const mainContents = () => {
    const win = getWindow();
    return win && !win.isDestroyed() ? win.webContents : null;
  };
  const fromMain = (event) => {
    const contents = mainContents();
    return Boolean(contents) && event?.sender === contents;
  };
  const listening = () => {
    const contents = mainContents();
    return Boolean(contents) && listener === contents && !contents.isDestroyed();
  };

  function push() {
    if (!listening()) return;
    const key = JSON.stringify(view);
    if (key === lastSent) return;
    lastSent = key;
    listener.send(UPDATE_VIEW_CHANNEL, view);
  }

  function forget(contents) {
    if (listener === contents) {
      listener = null;
      lastSent = '';
    }
  }

  ipcMain.handle(UPDATE_SUBSCRIBE_CHANNEL, (event) => {
    if (!fromMain(event)) return null;
    const contents = event.sender;
    if (!watched.has(contents)) {
      watched.add(contents);
      // A reload or a crash: the new page must subscribe again to count.
      contents.on('did-navigate', () => forget(contents));
      contents.on('render-process-gone', () => forget(contents));
    }
    listener = contents;
    lastSent = JSON.stringify(view);
    return view;
  });

  ipcMain.handle(UPDATE_ACT_CHANNEL, (event, request) => {
    if (!fromMain(event)) return { ok: false, error: 'only the main Nova window can answer the update notice' };
    const action = String(request?.action ?? '');
    const handler = handlers.get(action);
    if (!handler) return { ok: false, error: `unknown update action: ${action}` };
    // Never awaited: a download runs for minutes, and Restart quits the app.
    void Promise.resolve()
      .then(() => handler(request))
      .catch((err) => logger.error(`update action ${action} failed: ${errorLine(err)}`));
    return { ok: true };
  });

  return {
    /** Replace one part of the view (`installed` | `notice` | `whats_new`) and push it. */
    set(part, value) {
      view = { ...view, [part]: value };
      push();
    },
    view: () => view,
    /** What to do when the renderer sends `action`. */
    on(action, handler) {
      handlers.set(action, handler);
    },
    /** The main window's page subscribed and has not navigated away since. */
    hasListener: listening,
  };
}
