/**
 * Preload for the hidden clip export page only (ADR 039; CommonJS for the
 * Electron sandbox). Channel names are clipExporter.mjs's, repeated here
 * because a sandboxed preload cannot import it. The page reads sources and
 * writes the MP4 only through these calls, by the tokens a job names; the
 * main process accepts them from that window alone.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('novaClipExport', {
  onJob: (callback) => ipcRenderer.on('nova:clip-export:job', (_event, job) => callback(job)),
  onCancel: (callback) => ipcRenderer.on('nova:clip-export:cancel', (_event, msg) => callback(msg)),
  onPreview: (callback) => ipcRenderer.on('nova:clip-export:preview', (_event, req) => callback(req)),
  ready: () => ipcRenderer.send('nova:clip-export:ready'),
  /** Bytes `[start, end)` of a job's source. */
  read: (token, start, end) => ipcRenderer.invoke('nova:clip-export:read', { token, start, end }),
  /** Write `data` at `position` of the running job's MP4. */
  write: (jobId, position, data) => ipcRenderer.invoke('nova:clip-export:write', { job_id: jobId, position, data }),
  progress: (jobId, doneSec) => ipcRenderer.send('nova:clip-export:progress', { job_id: jobId, done_sec: doneSec }),
  done: (jobId, ok, error) => ipcRenderer.send('nova:clip-export:done', { job_id: jobId, ok, error: error ?? null }),
  previewDone: (reqId, result) => ipcRenderer.send('nova:clip-export:preview-done', { req_id: reqId, ...result }),
});
