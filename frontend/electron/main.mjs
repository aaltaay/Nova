/**
 * Electron main process — Windows desktop shell for Nova.
 * Spawns the local FastAPI sidecar, then loads the Vite UI.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow, ipcMain, shell } from 'electron';
import {
  API_BASE,
  openEnvFileIfNeeded,
  restartApiSidecar,
  startApiSidecar,
  stopApiSidecar,
  waitForHealth,
} from './sidecar.mjs';
import { openOrFocusTraderWindow } from './traderWindows.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isDev = !app.isPackaged;
const ALLOWED_EXTERNAL_HOSTS = new Set(['www.interactivebrokers.com']);

/** @type {BrowserWindow | null} */
let mainWindow = null;

function windowOptions() {
  return {
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
  };
}

/** Stock View double-click opens ?view=stock&symbol=… in a real child window. */
function attachStockViewWindowOpen(win) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    try {
      openOrFocusTraderWindow(url, windowOptions(), attachStockViewWindowOpen);
    } catch {
      /* invalid or non-trader URL */
    }
    return { action: 'deny' };
  });
}

function createWindow() {
  mainWindow = new BrowserWindow(windowOptions());

  if (isDev) {
    const viteUrl = process.env.NOVA_VITE_URL || 'http://127.0.0.1:5173';
    void mainWindow.loadURL(viteUrl);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    void mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  attachStockViewWindowOpen(mainWindow);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('app:version', () => app.getVersion());
ipcMain.handle('nova:apiBase', () => API_BASE);

ipcMain.handle('nova:restartApi', async () => {
  try {
    await restartApiSidecar();
    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('[nova] restartApi failed', message);
    return { ok: false, error: message };
  }
});

ipcMain.handle('nova:openStockView', (_event, url) => {
  if (typeof url !== 'string' || !url.startsWith('http')) {
    throw new Error('Invalid Trader URL');
  }
  return openOrFocusTraderWindow(url, windowOptions(), attachStockViewWindowOpen);
});

ipcMain.handle('nova:openExternal', async (_event, url) => {
  const parsed = new URL(String(url));
  if (
    parsed.protocol !== 'https:'
    || !ALLOWED_EXTERNAL_HOSTS.has(parsed.hostname)
  ) {
    throw new Error('External URL is not allowed');
  }
  await shell.openExternal(parsed.toString());
  return true;
});

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
