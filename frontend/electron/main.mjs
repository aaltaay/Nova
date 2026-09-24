/**
 * Electron main process — Windows desktop shell for Nova.
 * Spawns the local FastAPI sidecar, then loads the Vite UI.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow, desktopCapturer, ipcMain, powerMonitor, screen, shell } from 'electron';
import { shouldOpenDetachedDevTools } from './devtoolsGate.mjs';
import {
  API_BASE,
  getDesktopApiKey,
  getDesktopEnvPath,
  openEnvFileIfNeeded,
  reloadEngine,
  restartApiSidecar,
  startApiSidecar,
  stopApiSidecar,
  stopApiSidecarForUpdate,
  waitForHealth,
} from './sidecar.mjs';
import { startAutoUpdate } from './autoUpdate.mjs';
import { startPerfMetrics } from './perfMetrics.mjs';
import { startFocusSensor } from './focusSensor.mjs';
import { startScreenRecorder } from './screenRecorder.mjs';
import { createScreenRecordBridge } from './screenRecordBridge.mjs';
import { applyGpuPolicy } from './gpuPolicy.mjs';
import { attachRendererGuards, recoverWindowIfErrorPage } from './rendererGuards.mjs';
import { applySingleInstance, focusExistingWindow } from './singleInstance.mjs';
import { skipApiSidecar } from './sidecarSkip.mjs';
import { engineStep, openStartupSplash, STARTUP_STEPS } from './startupSplash.mjs';
import { isAllowedRendererUrl, loadHostWindow } from './traderWindowLoad.mjs';
import { openOrFocusTraderWindow } from './traderWindows.mjs';
import {
  WINDOW_ID_MAIN,
  applyStoredPlacement,
  bindWindowBoundsPersist,
  restoreWindowPlacement,
} from './windowBounds.mjs';
import { formatScannerWindowTitle } from './appTitle.mjs';
import { novaDesktopReleaseTag } from './loadReleaseTag.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
applyGpuPolicy(app);
const isDev = !app.isPackaged;
const ALLOWED_EXTERNAL_HOSTS = new Set(['www.interactivebrokers.com']);
// Title bar and taskbar; the packed exe carries the same icon (electron-builder).
const APP_ICON = path.join(__dirname, 'build', 'icon.ico');

/** @type {BrowserWindow | null} */
let mainWindow = null;
/** The "Starting Nova" window until the desk shows. */
let startup = null;
let quitting = false;
/** ADR 035: every monitor, recorded from launch to quit. */
let screenRecorder = null;
let screenRecordBridge = null;

/** The trading screen is always recorded; nothing but a quit stops it (operator decision 2026-09-24). */
function startScreenRecording() {
  screenRecordBridge = createScreenRecordBridge({
    ipcMain,
    BrowserWindow,
    isRecorderWindow: (w) => Boolean(screenRecorder?.isRecorderWindow(w)),
    apiBase: API_BASE,
    apiKey: getDesktopApiKey,
  });
  screenRecorder = startScreenRecorder({
    BrowserWindow,
    desktopCapturer,
    screen,
    powerMonitor,
    ipcMain,
    userData: app.getPath('userData'),
    onView: (view) => screenRecordBridge?.publish(view),
  });
}

/** Windows the operator can see or close -- the hidden screen recorder is not one. */
function deskWindowCount() {
  return BrowserWindow.getAllWindows().filter((w) => !screenRecorder?.isRecorderWindow(w)).length;
}

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
    icon: APP_ICON,
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

/** Where the desk will open: its saved placement, else the primary work area. */
function deskTarget() {
  const saved = restoreWindowPlacement(app.getPath('userData'), WINDOW_ID_MAIN, displayWorkAreas());
  return saved?.bounds ?? screen.getPrimaryDisplay().workArea;
}

function createWindow() {
  const userData = app.getPath('userData');
  const saved = restoreWindowPlacement(userData, WINDOW_ID_MAIN, displayWorkAreas());
  mainWindow = new BrowserWindow({
    ...windowOptions(),
    ...(saved?.bounds || {}),
    show: false,
  });
  applyStoredPlacement(mainWindow, saved);
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
    // A different engine process answers, or reloadEngine says why not (never a false "reloaded").
    const { from, to } = await reloadEngine();
    return { ok: true, from, to };
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
    if (!mainWindow && startup?.window) {
      focusExistingWindow(startup.window);
      return;
    }
    focusExistingWindow(mainWindow, (win) => {
      recoverWindowIfErrorPage(win, mainRecoverOpts());
    });
  })
) {
  app.quit();
} else {
  app.whenReady().then(async () => {
    // Nothing else of Nova is on screen until the engine answers and the desk loads.
    startup = openStartupSplash({
      BrowserWindow,
      target: deskTarget(),
      version: novaDesktopReleaseTag(app),
      icon: APP_ICON,
      // Closing it calls the launch off, even while the desk loads hidden.
      onCancel: () => app.quit(),
    });
    // Recording needs no engine: it starts with the app, before the desk.
    startScreenRecording();
    try {
      startup.step(engineStep(await startApiSidecar()));
      await openEnvFileIfNeeded();
      await waitForHealth();
      // The operator closed the starting window: the launch is called off.
      if (quitting) return;
      startup.step(STARTUP_STEPS.loading);
      createWindow();
      startup.closeWhenShown(mainWindow);
      // ADR 026: CPU / memory per window process, every 5 s. Measures only.
      const stopPerfMetrics = startPerfMetrics({
        app,
        BrowserWindow,
        apiBase: API_BASE,
        apiKey: getDesktopApiKey,
        releaseTag: novaDesktopReleaseTag(app),
      });
      app.on('will-quit', stopPerfMetrics);
      // ADR 033: which Nova window Windows has in front and each window's monitor (GET /sensors/focus).
      const stopFocusSensor = startFocusSensor({
        app,
        BrowserWindow,
        screen,
        apiBase: API_BASE,
        apiKey: getDesktopApiKey,
      });
      app.on('will-quit', stopFocusSensor);
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
      if (quitting) return;
      const { dialog } = await import('electron');
      await dialog.showErrorBox(
        'Nova failed to start',
        err instanceof Error ? err.message : String(err),
      );
      startup.close();
      app.quit();
    }

    app.on('activate', () => {
      if (deskWindowCount() === 0) createWindow();
    });
  });
}

function lastWindowClosed() {
  stopApiSidecar();
  if (process.platform !== 'darwin') app.quit();
}

app.on('window-all-closed', lastWindowClosed);

// The hidden recorder window keeps 'window-all-closed' from firing: closing the
// last window the operator can see is what ends Nova.
app.on('browser-window-created', (_event, win) => {
  win.once('closed', () => {
    if (!quitting && !screenRecorder?.isRecorderWindow(win) && deskWindowCount() === 0) lastWindowClosed();
  });
});

app.on('before-quit', () => {
  quitting = true;
  screenRecorder?.stop('quit');
  screenRecordBridge?.stop();
  stopApiSidecar();
});
