/**
 * The header mute on the desktop (architecture/schema/desk-ops.md, "The desk's voice and the header mute"): every
 * Nova window's audio follows the desk's one switch -- the stream's pop-out too, which runs no Nova code. The page
 * owns the switch (`nova.desk.sound.muted`) and tells the main process here; a window opened later starts with it.
 * The voice (speechSynthesis) is the computer's own speech, not a window's audio: the page silences it itself.
 *
 * The sound menu's YouTube row reaches the pop-out here too: its switch mutes that window alone, and its volume is
 * asked of YouTube's player there (`streamVolumeScript`). Owner: main.mjs wires it.
 */

export const DESK_SOUND_CHANNEL = 'nova:sound:muted';
export const DESK_STREAM_SOUND_CHANNEL = 'nova:sound:stream';
export const DESK_STREAM_STATE_CHANNEL = 'nova:stream:state';
export const DESK_STREAM_WINDOW_CHANNEL = 'nova:stream:window';
export const DESK_STREAM_SWITCH_CHANNEL = 'nova:stream:switch';

let muted = false;
/** The pop-out plays with sound until the page says otherwise. */
let streamOn = true;
let streamLevel = null;

export function deskSoundMuted() {
  return muted;
}

/** YouTube's own player when it is up, the page's video otherwise; `level` is a whole number, never text. */
export function streamVolumeScript(level) {
  const n = Math.max(0, Math.min(100, Math.round(Number(level) || 0)));
  return `(() => { const p = document.getElementById('movie_player'); if (p && p.setVolume) p.setVolume(${n});`
    + ` const v = document.querySelector('video'); if (v) v.volume = ${n / 100}; })()`;
}

function isStream(win, streamWindow) {
  return win === streamWindow?.();
}

function applyTo(win, streamWindow) {
  if (!win || win.isDestroyed?.()) return;
  try {
    win.webContents.setAudioMuted(muted || (isStream(win, streamWindow) && !streamOn));
  } catch (err) {
    console.warn('[nova] could not set a window\'s sound', err);
  }
}

function applyStreamLevel(win) {
  if (!win || win.isDestroyed?.() || streamLevel === null) return;
  win.webContents.executeJavaScript(streamVolumeScript(streamLevel))
    .catch((err) => console.warn('[nova] could not set the stream\'s volume', err));
}

/** The pop-out has one switch: the other pages' rows follow it, so none sends an old one back. */
function tellOtherPages(BrowserWindow, sender, popOut) {
  for (const win of BrowserWindow.getAllWindows()) {
    if (win === popOut || win.isDestroyed?.() || win.webContents === sender) continue;
    win.webContents.send(DESK_STREAM_SWITCH_CHANNEL, streamOn);
  }
}

/** Every window now, and each one opened later. `streamWindow` answers the pop-out, or null. */
export function wireDeskSound({ ipcMain, app, BrowserWindow, streamWindow }) {
  ipcMain.on(DESK_SOUND_CHANNEL, (_event, next) => {
    const value = next === true;
    if (value === muted) return;
    muted = value;
    for (const win of BrowserWindow.getAllWindows()) applyTo(win, streamWindow);
  });
  ipcMain.on(DESK_STREAM_SOUND_CHANNEL, (event, next) => {
    streamOn = next?.on === true;
    streamLevel = Number.isFinite(next?.level) ? next.level : streamLevel;
    const win = streamWindow?.();
    applyTo(win, streamWindow);
    applyStreamLevel(win);
    if (win) tellOtherPages(BrowserWindow, event.sender, win);
  });
  ipcMain.handle(DESK_STREAM_STATE_CHANNEL, () => ({ open: Boolean(streamWindow?.()), on: streamOn }));
  app.on('browser-window-created', (_event, win) => applyTo(win, streamWindow));
}

/** Tell the pages the pop-out opened or closed, so the row and the in-page player follow. */
export function announceStreamWindow(BrowserWindow, open) {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed?.()) win.webContents.send(DESK_STREAM_WINDOW_CHANNEL, open);
  }
}

/** Test-only. */
export function resetDeskSoundForTests() {
  muted = false;
  streamOn = true;
  streamLevel = null;
}
