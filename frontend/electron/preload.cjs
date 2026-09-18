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
  /** Kill + restart the local FastAPI sidecar when the UI shows Backend unreachable. */
  restartApi: () => ipcRenderer.invoke('nova:restartApi'),
});
