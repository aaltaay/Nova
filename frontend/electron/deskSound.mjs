/**
 * The header mute on the desktop (architecture/schema/desk-ops.md, "The desk's voice and the header mute"): every
 * Nova window's audio follows the desk's one switch -- the stream's pop-out too, which runs no Nova code. The page
 * owns the switch (`nova.desk.sound.muted`) and tells the main process here; a window opened later starts with it.
 * The voice (speechSynthesis) is the computer's own speech, not a window's audio: the page silences it itself.
 * Owner: main.mjs wires it.
 */

export const DESK_SOUND_CHANNEL = 'nova:sound:muted';

let muted = false;

export function deskSoundMuted() {
  return muted;
}

function applyTo(win) {
  if (!win || win.isDestroyed?.()) return;
  try {
    win.webContents.setAudioMuted(muted);
  } catch (err) {
    console.warn('[nova] could not set a window\'s sound', err);
  }
}

/** Every window now, and each one opened later. */
export function wireDeskSound({ ipcMain, app, BrowserWindow }) {
  ipcMain.on(DESK_SOUND_CHANNEL, (_event, next) => {
    const value = next === true;
    if (value === muted) return;
    muted = value;
    for (const win of BrowserWindow.getAllWindows()) applyTo(win);
  });
  app.on('browser-window-created', (_event, win) => applyTo(win));
}

/** Test-only. */
export function resetDeskSoundForTests() {
  muted = false;
}
