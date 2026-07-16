/**
 * Preload bridge (CommonJS — required for Electron sandbox preload).
 */
const { contextBridge, ipcRenderer } = require('electron');

const API_BASE = 'http://127.0.0.1:8000';

contextBridge.exposeInMainWorld('novaDesktop', {
  isDesktop: true,
  apiBase: API_BASE,
  getVersion: () => ipcRenderer.invoke('app:version'),
  /** Open Stock View in a dedicated BrowserWindow (double-click / Stock View btn). */
  openStockView: (url) => ipcRenderer.invoke('nova:openStockView', url),
  /** Kill + restart the local FastAPI sidecar when the UI shows Backend unreachable. */
  restartApi: () => ipcRenderer.invoke('nova:restartApi'),
});
