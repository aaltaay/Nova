/**
 * Preload for the hidden screen recorder page only (ADR 035; CommonJS for the
 * Electron sandbox). Channel names are screenRecorder.mjs's, repeated here
 * because a sandboxed preload cannot import it. The main process accepts these
 * messages from the recorder window alone, so no desk page can write a file.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('novaScreenRecorder', {
  onCommand: (callback) => {
    ipcRenderer.on('nova:screen-rec:cmd', (_event, cmd) => callback(cmd));
  },
  ready: () => ipcRenderer.send('nova:screen-rec:ready'),
  /** One MediaRecorder chunk; `bytes` is null when the timeslice carried no data (still proof of life). */
  chunk: (id, bytes) => ipcRenderer.send('nova:screen-rec:chunk', { id, bytes }),
  event: (event) => ipcRenderer.send('nova:screen-rec:event', event),
});
