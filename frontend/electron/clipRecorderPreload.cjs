/**
 * Preload for the hidden high-quality clip capture page only (ADR 039;
 * CommonJS for the Electron sandbox). Channel names are clipHq.mjs's, repeated
 * here because a sandboxed preload cannot import it. The main process accepts
 * these messages from that window alone, so no desk page can write a file.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('novaClipRecorder', {
  onCommand: (callback) => {
    ipcRenderer.on('nova:clip-rec:cmd', (_event, cmd) => callback(cmd));
  },
  ready: () => ipcRenderer.send('nova:clip-rec:ready'),
  /** One MediaRecorder chunk; `bytes` is null when the timeslice carried no data (still proof of life). */
  chunk: (id, bytes) => ipcRenderer.send('nova:clip-rec:chunk', { id, bytes }),
  event: (event) => ipcRenderer.send('nova:clip-rec:event', event),
});
