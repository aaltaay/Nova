/**
 * The "Starting Nova" window.
 *
 * The desk window is created only once the local engine answers /api/health,
 * and shown only once its page has loaded. On a cold start -- no engine already
 * on :8000 -- that is a 2.5 s look for one, the engine's own start and the page
 * load, with nothing of Nova on screen: the same silence that made "Restart to
 * update" read as "nothing happened" (2026-09-23). This small window opens as
 * soon as Electron is ready, names the step main.mjs is on, and closes the
 * moment the desk window shows. After an update it also takes over from the
 * "Updating Nova" window (updateSplash.ps1), which closes once any new Nova
 * window is visible.
 *
 * It is a page with no preload and no Node access; main.mjs writes each step
 * into it. The operator closing it calls the launch off (`onCancel`) -- even
 * once the desk window exists, hidden while its page loads, which would
 * otherwise keep Nova running and show the desk anyway. Nova's own close is
 * destroy(), which never emits 'close', so it is never read as the operator's.
 */

export const STARTUP_SPLASH_WIDTH = 420;
export const STARTUP_SPLASH_HEIGHT = 150;

/** The desk's own colours (main.mjs backgroundColor #0b0f14). */
const BG = '#0b0f14';

export const STARTUP_STEPS = Object.freeze({
  looking: 'Looking for the local engine…',
  starting: 'Starting the local engine…',
  connecting: 'Connecting to the local engine…',
  loading: 'Loading the desk…',
});

/** The step after startApiSidecar(): Nova started an engine, or found one already running. */
export function engineStep(engine) {
  return engine === 'spawned' ? STARTUP_STEPS.starting : STARTUP_STEPS.connecting;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

/**
 * A JavaScript string literal for code run in the page: JSON.stringify, plus
 * every character JSON leaves raw that could end a script or a line there.
 */
export function jsString(text) {
  return JSON.stringify(String(text)).replace(
    /[<>/\u2028\u2029]/g,
    (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`,
  );
}

/** The whole page. No script: the steps are written in from the main process. */
export function splashHtml(version = '') {
  const title = escapeHtml(version ? `Starting Nova ${version}` : 'Starting Nova');
  return `<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Starting Nova</title>
<style>
  html, body { margin: 0; height: 100%; background: ${BG}; color: #e6edf3; overflow: hidden;
    font: 13px "Segoe UI", system-ui, sans-serif; -webkit-user-select: none; user-select: none; }
  body { box-sizing: border-box; border: 1px solid #303842; padding: 18px 22px; }
  h1 { font-size: 16px; font-weight: 600; margin: 0 0 10px; }
  #step { margin: 0 0 10px; }
  .bar { position: relative; height: 4px; background: #1f262e; border-radius: 2px; overflow: hidden; margin: 0 0 12px; }
  .bar::after { content: ""; position: absolute; top: 0; left: -35%; width: 35%; height: 100%;
    background: #3fb950; border-radius: 2px; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { to { left: 100%; } }
  p.note { margin: 0; color: #8b949e; font-size: 12px; }
</style></head>
<body>
  <h1>${title}</h1>
  <p id="step">${escapeHtml(STARTUP_STEPS.looking)}</p>
  <div class="bar"></div>
  <p class="note">The desk opens as soon as its local engine answers.</p>
</body></html>`;
}

/**
 * Centre the window on the rect the desk will open in (its saved placement),
 * else the primary display's work area, kept inside that area.
 */
export function splashBounds(target, width = STARTUP_SPLASH_WIDTH, height = STARTUP_SPLASH_HEIGHT) {
  const x = Math.round(target.x + (target.width - width) / 2);
  const y = Math.round(target.y + (target.height - height) / 2);
  return {
    x: Math.max(target.x, x),
    y: Math.max(target.y, y),
    width,
    height,
  };
}

/**
 * Open the window. Never throws: without it Nova starts as before, silently.
 * @param {{ BrowserWindow: any, target: {x: number, y: number, width: number, height: number},
 *   version?: string, icon?: string, onCancel?: () => void }} opts
 * @returns {{ window: any, step: (text: string) => void, closeWhenShown: (desk: any) => void,
 *   close: () => void }}
 */
export function openStartupSplash({ BrowserWindow, target, version = '', icon, onCancel }) {
  let win = null;
  let lastStep = STARTUP_STEPS.looking;
  const alive = () => win && !win.isDestroyed();
  const writeStep = () => {
    if (!alive()) return;
    const js = `(() => { const el = document.getElementById('step'); if (el) el.textContent = ${jsString(lastStep)}; })()`;
    win.webContents.executeJavaScript(js).catch(() => {
      // Still loading or already closed: did-finish-load writes the latest step.
    });
  };
  try {
    win = new BrowserWindow({
      width: STARTUP_SPLASH_WIDTH,
      height: STARTUP_SPLASH_HEIGHT,
      frame: false,
      resizable: false,
      maximizable: false,
      fullscreenable: false,
      show: false,
      title: 'Starting Nova',
      backgroundColor: BG,
      ...(icon ? { icon } : {}),
      webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    // Constructor bounds scale on a display whose DPI differs from the primary's;
    // setBounds after creation lands exactly (windowBounds.mjs).
    win.setBounds(splashBounds(target));
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', (event) => event.preventDefault());
    // A step that arrived while the page loaded.
    win.webContents.on('did-finish-load', writeStep);
    // Only the operator's close emits 'close' (Nova's own is destroy()).
    win.on('close', () => onCancel?.());
    win.once('ready-to-show', () => {
      if (alive()) win.show();
    });
    void win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splashHtml(version))}`).catch((err) => {
      console.error('[nova] starting window failed to load', err);
    });
  } catch (err) {
    console.error('[nova] starting window unavailable', err);
    win = null;
  }

  const close = () => {
    if (alive()) win.destroy();
  };
  return {
    get window() {
      return alive() ? win : null;
    },
    step(text) {
      lastStep = String(text);
      writeStep();
    },
    /** Close once the desk is on screen, or gone. */
    closeWhenShown(desk) {
      if (!desk || desk.isDestroyed() || desk.isVisible()) {
        close();
        return;
      }
      desk.once('show', close);
      desk.once('closed', close);
    },
    close,
  };
}
