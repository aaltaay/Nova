/**
 * Preload bridge (CommonJS — required for Electron sandbox preload).
 */
const { contextBridge, ipcRenderer } = require('electron');

const API_BASE = 'http://127.0.0.1:8000';
// Same NOVA_API_KEY the API loaded -- never a second secret, never baked into dist.
const apiKey = ipcRenderer.sendSync('nova:apiKeySync') || '';

contextBridge.exposeInMainWorld('novaDesktop', {
  isDesktop: true,
  apiBase: API_BASE,
  apiKey,
  getVersion: () => ipcRenderer.invoke('app:version'),
  /** Open Stock View in a dedicated BrowserWindow (double-click / Stock View btn). */
  openStockView: (url) => ipcRenderer.invoke('nova:openStockView', url),
  /** Open an allowlisted HTTPS URL in the system browser. */
  openExternal: (url) => ipcRenderer.invoke('nova:openExternal', url),
  /** The followed traders' stream in a small window of its own (an 11-character YouTube id only). */
  openStream: (videoId) => ipcRenderer.invoke('nova:openStream', videoId),
  /** Google's own sign-in page in a window of its own, so the stream player gets past YouTube's bot check. */
  youtubeSignIn: () => ipcRenderer.invoke('nova:youtubeSignIn'),
  /** Called when that sign-in window closes (true when it reached YouTube signed in); returns the unsubscribe. */
  onYoutubeSignedIn: (cb) => {
    const listener = (_event, signedIn) => cb(Boolean(signedIn));
    ipcRenderer.on('nova:youtube:signedIn', listener);
    return () => ipcRenderer.removeListener('nova:youtube:signedIn', listener);
  },
  /** The header mute (electron/deskSound.mjs): every Nova window's audio follows it. Channel repeated (sandboxed preload). */
  setSoundMuted: (muted) => ipcRenderer.send('nova:sound:muted', muted === true),
  /** Kill + restart the local FastAPI sidecar when the UI shows Backend unreachable. */
  restartApi: () => ipcRenderer.invoke('nova:restartApi'),
  /**
   * The update notice and What's new card (electron/updateBridge.mjs). `subscribe`
   * calls back with the current view, then with every change; it returns the
   * unsubscribe. Channel names are updateBridge.mjs's, repeated here because a
   * sandboxed preload cannot import it.
   */
  updates: {
    subscribe: (onView) => {
      const listener = (_event, view) => onView(view);
      ipcRenderer.on('nova:update:view', listener);
      ipcRenderer
        .invoke('nova:update:subscribe')
        .then((view) => {
          if (view) onView(view);
        })
        .catch((err) => console.warn('[nova] update notice unavailable', err));
      return () => ipcRenderer.removeListener('nova:update:view', listener);
    },
    act: (request) => ipcRenderer.invoke('nova:update:act', request),
  },
  /**
   * The trading screen recording's status (electron/screenRecordBridge.mjs,
   * ADR 035). Read-only: no page can stop the recording. Same contract as
   * `updates.subscribe`.
   */
  screenRecord: {
    subscribe: (onView) => {
      const listener = (_event, view) => onView(view);
      ipcRenderer.on('nova:screen-record:view', listener);
      ipcRenderer
        .invoke('nova:screen-record:subscribe')
        .then((view) => {
          if (view) onView(view);
        })
        .catch((err) => console.warn('[nova] screen recording status unavailable', err));
      return () => ipcRenderer.removeListener('nova:screen-record:view', listener);
    },
  },
  /**
   * Share clips (electron/clipBridge.mjs, ADR 039): the view, the operator's
   * requests, and this window's Trader tab report. Same subscribe contract as
   * `screenRecord`.
   */
  clips: {
    subscribe: (onView) => {
      const listener = (_event, view) => onView(view);
      ipcRenderer.on('nova:clips:view', listener);
      ipcRenderer
        .invoke('nova:clips:subscribe')
        .then((view) => {
          if (view) onView(view);
        })
        .catch((err) => console.warn('[nova] clips unavailable', err));
      return () => ipcRenderer.removeListener('nova:clips:view', listener);
    },
    act: (request) => ipcRenderer.invoke('nova:clips:act', request),
    report: (report) => ipcRenderer.send('nova:clips:tab', report),
  },
});
