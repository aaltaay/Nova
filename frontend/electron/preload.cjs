/**
 * Preload bridge (CommonJS — required for Electron sandbox preload).
 */
const { contextBridge, ipcRenderer } = require('electron');

const API_BASE = 'http://127.0.0.1:8000';

contextBridge.exposeInMainWorld('novaDesktop', {
  isDesktop: true,
  apiBase: API_BASE,
  getVersion: () => ipcRenderer.invoke('app:version'),
});
