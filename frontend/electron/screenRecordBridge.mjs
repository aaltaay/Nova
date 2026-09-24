/**
 * The trading screen recording's status (ADR 035), out of the main process:
 * to every desk window over IPC (the header chip, frontend/src/screen_record/)
 * and to the backend (`POST /api/screen-record`, read by the diagnostics
 * checklist and by agents). Read-only for every reader: nothing a page sends
 * can start, stop or pause the recording.
 *
 * Windows get each new view (a desk window subscribes, then hears every
 * change); the backend gets one every SCREEN_RECORD_REPORT_MS and at once when
 * the state changes. A failed post is logged at debug level at most once a
 * minute and never throws. Electron and the API are passed in (main.mjs).
 */
import { SCREEN_RECORD_REPORT_MS } from './screenRecordPlan.mjs';

export const SCREEN_RECORD_VIEW_CHANNEL = 'nova:screen-record:view';
export const SCREEN_RECORD_SUBSCRIBE_CHANNEL = 'nova:screen-record:subscribe';
const SCREEN_RECORD_REPORT_PATH = '/api/screen-record';
const REPORT_FAIL_LOG_MS = 60_000;
/** Mirrors constantGroups/api_auth.ts NOVA_API_KEY_HEADER. */
const NOVA_API_KEY_HEADER = 'X-Nova-Api-Key';
/** A desk page; the starting splash is a data: page and the recorder page is not a desk. */
const DESK_URL = /^(https?|file):/i;

export function createScreenRecordBridge({
  ipcMain,
  BrowserWindow,
  isRecorderWindow = () => false,
  apiBase,
  apiKey = () => '',
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  timers = globalThis,
  intervalMs = SCREEN_RECORD_REPORT_MS,
}) {
  let view = null;
  let lastState = null;
  let lastPost = -Infinity;
  let inFlight = false;
  let lastFailLog = -Infinity;

  const deskContents = () =>
    BrowserWindow.getAllWindows()
      .filter((w) => !w.isDestroyed() && !isRecorderWindow(w))
      .map((w) => w.webContents)
      .filter((c) => {
        try {
          return !c.isDestroyed() && DESK_URL.test(String(c.getURL() || ''));
        } catch {
          return false; // a window closing mid-read has no page to tell
        }
      });

  ipcMain.handle(SCREEN_RECORD_SUBSCRIBE_CHANNEL, () => view);

  const noteFailure = (why) => {
    const t = now();
    if (t - lastFailLog < REPORT_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[nova] screen recording status not delivered to the backend', why);
  };

  function post() {
    if (!view || inFlight) return;
    lastPost = now();
    const headers = { 'Content-Type': 'application/json' };
    const key = apiKey();
    if (key) headers[NOVA_API_KEY_HEADER] = key;
    inFlight = true;
    try {
      Promise.resolve(
        fetchImpl(`${apiBase}${SCREEN_RECORD_REPORT_PATH}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(view),
          signal: AbortSignal.timeout(intervalMs),
        }),
      )
        .then((res) => {
          if (!res.ok) noteFailure(`HTTP ${res.status}`);
        }, noteFailure)
        .finally(() => {
          inFlight = false;
        });
    } catch (err) {
      inFlight = false;
      noteFailure(err);
    }
  }

  const timer = timers.setInterval(() => post(), intervalMs);
  timer.unref?.();

  return {
    publish(next) {
      view = next;
      for (const contents of deskContents()) contents.send(SCREEN_RECORD_VIEW_CHANNEL, view);
      if (next?.state !== lastState || now() - lastPost >= intervalMs) {
        lastState = next?.state ?? null;
        post();
      }
    },
    view: () => view,
    stop() {
      timers.clearInterval(timer);
      ipcMain.removeHandler?.(SCREEN_RECORD_SUBSCRIBE_CHANNEL);
    },
  };
}
