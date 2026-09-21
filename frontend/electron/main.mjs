/**
 * Electron main process — Windows desktop shell for Nova.
 * Spawns the local FastAPI sidecar, then loads the Vite UI.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow, ipcMain, screen, shell } from 'electron';
import { shouldOpenDetachedDevTools } from './devtoolsGate.mjs';
import {
  API_BASE,
  getDesktopApiKey,
  getDesktopEnvPath,
  openEnvFileIfNeeded,
  restartApiSidecar,
  startApiSidecar,
  stopApiSidecar,
  stopApiSidecarForUpdate,
  waitForHealth,
} from './sidecar.mjs';
import { startAutoUpdate } from './autoUpdate.mjs';
import { applyGpuPolicy } from './gpuPolicy.mjs';
import { attachRendererGuards, recoverWindowIfErrorPage } from './rendererGuards.mjs';
import { applySingleInstance, focusExistingWindow } from './singleInstance.mjs';
import { skipApiSidecar } from './sidecarSkip.mjs';
import { isAllowedRendererUrl, loadHostWindow } from './traderWindowLoad.mjs';
import { openOrFocusTraderWindow } from './traderWindows.mjs';
import {
  WINDOW_ID_MAIN,
  bindWindowBoundsPersist,
  restoreWindowBounds,
} from './windowBounds.mjs';
import { formatScannerWindowTitle } from './appTitle.mjs';
import { novaDesktopReleaseTag } from './loadReleaseTag.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
applyGpuPolicy(app);
const isDev = !app.isPackaged;
const ALLOWED_EXTERNAL_HOSTS = new Set(['www.interactivebrokers.com']);

/** @type {BrowserWindow | null} */
let mainWindow = null;

function displayWorkAreas() {
  return screen.getAllDisplays().map((d) => ({
    x: d.workArea.x,
    y: d.workArea.y,
    width: d.workArea.width,
    height: d.workArea.height,
  }));
}

function windowOptions() {
  return {
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: formatScannerWindowTitle(novaDesktopReleaseTag(app)),
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
    if (!isAllowedRendererUrl(url, { requireStockView: true })) {
      return { action: 'deny' };
    }
    void openOrFocusTraderWindow(url, windowOptions(), attachStockViewWindowOpen).catch(
      (err) => {
        console.error('[nova] open trader window failed', err);
      },
    );
    return { action: 'deny' };
  });
}

function packagedIndexHtml() {
  return path.join(__dirname, '..', 'dist', 'index.html');
}

function viteUrl() {
  return process.env.NOVA_VITE_URL || 'http://127.0.0.1:5173';
}

function mainRecoverOpts() {
  return isDev
    ? { reloadUrl: viteUrl(), loadFilePath: null, allowedBase: viteUrl() }
    : { reloadUrl: null, loadFilePath: packagedIndexHtml(), allowedBase: 'file:' };
}

function createWindow() {
  const userData = app.getPath('userData');
  const saved = restoreWindowBounds(userData, WINDOW_ID_MAIN, displayWorkAreas());
  mainWindow = new BrowserWindow({
    ...windowOptions(),
    ...(saved || {}),
    show: false,
  });
  bindWindowBoundsPersist(mainWindow, userData, WINDOW_ID_MAIN);
  const recover = mainRecoverOpts();
  attachRendererGuards(mainWindow, { ...recover, retryFail: true });
  void loadHostWindow(mainWindow, recover).then((ok) => {
    if (!ok) recoverWindowIfErrorPage(mainWindow, recover);
    if (shouldOpenDetachedDevTools(isDev) && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.openDevTools({ mode: 'detach' });
    }
  });
  attachStockViewWindowOpen(mainWindow);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('app:version', () => app.getVersion());
ipcMain.handle('nova:apiBase', () => API_BASE);
ipcMain.on('nova:apiKeySync', (event) => {
  event.returnValue = getDesktopApiKey();
});

ipcMain.handle('nova:restartApi', async () => {
  if (skipApiSidecar()) {
    return {
      ok: false,
      error:
        'NOVA_SKIP_API_SIDECAR=1 -- will not recycle :8000. Reload the morning API if you changed backend.',
    };
  }
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
  if (!isAllowedRendererUrl(url, { requireStockView: true })) {
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

if (
  !applySingleInstance(app, () => {
    focusExistingWindow(mainWindow, (win) => {
      recoverWindowIfErrorPage(win, mainRecoverOpts());
    });
  })
) {
  app.quit();
} else {
  app.whenReady().then(async () => {
    try {
      await startApiSidecar();
      await openEnvFileIfNeeded();
      await waitForHealth();
      createWindow();
      // Packaged Windows only; downloads in the background, installs only on
      // the operator's "Restart to update" (#347). Never throws.
      void startAutoUpdate({
        getWindow: () => mainWindow,
        envPath: getDesktopEnvPath,
        stopEngine: stopApiSidecarForUpdate,
        restartEngine: restartApiSidecar,
      });
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
}

app.on('window-all-closed', () => {
  stopApiSidecar();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopApiSidecar();
});
