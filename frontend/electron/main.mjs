/**
 * Electron main process — Windows desktop shell for Nova.
 * Spawns the local FastAPI sidecar, then loads the Vite UI.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow, ipcMain } from 'electron';
import {
  API_BASE,
  openEnvFileIfNeeded,
  startApiSidecar,
  stopApiSidecar,
  waitForHealth,
} from './sidecar.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isDev = !app.isPackaged;

/** @type {BrowserWindow | null} */
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Nova',
    backgroundColor: '#0b0f14',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev) {
    const viteUrl = process.env.NOVA_VITE_URL || 'http://127.0.0.1:5173';
    void mainWindow.loadURL(viteUrl);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    void mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('app:version', () => app.getVersion());
ipcMain.handle('nova:apiBase', () => API_BASE);

app.whenReady().then(async () => {
  try {
    await startApiSidecar();
    await openEnvFileIfNeeded();
    await waitForHealth();
    createWindow();
  } catch (err) {
    console.error(err);
    const { dialog } = await import('electron');
    await dialog.showErrorBox(
      'Nova failed to start',
      err instanceof Error ? err.message : String(err),
    );
    app.quit();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopApiSidecar();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopApiSidecar();
});
