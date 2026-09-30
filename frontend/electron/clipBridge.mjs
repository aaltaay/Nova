/**
 * Share clips (ADR 039) out of the main process: the clip view to every desk
 * window over IPC (the Record menu, the CLIP chips, Records > Video clips),
 * each window's Trader tab report and the operator's requests in, and the view
 * to the backend (`POST /api/clips`, read by the checklist and by agents). A
 * request or a report is taken from a desk window only -- never from the
 * hidden recorder, capture or export pages. A failed post is logged at debug
 * level at most once a minute and never throws.
 */
import { CLIP_REPORT_MS } from './clipPlan.mjs';

export const CLIPS_VIEW_CHANNEL = 'nova:clips:view';
export const CLIPS_SUBSCRIBE_CHANNEL = 'nova:clips:subscribe';
export const CLIPS_ACT_CHANNEL = 'nova:clips:act';
export const CLIPS_TAB_CHANNEL = 'nova:clips:tab';
const CLIPS_REPORT_PATH = '/api/clips';
const REPORT_FAIL_LOG_MS = 60_000;
/** Mirrors constantGroups/api_auth.ts NOVA_API_KEY_HEADER. */
const NOVA_API_KEY_HEADER = 'X-Nova-Api-Key';
const DESK_URL = /^(https?|file):/i;

/** What changes the backend should hear at once (not on the next interval). */
const shapeKey = (v) => JSON.stringify([
  (v?.open || []).map((o) => [o.clip_id, o.state, Boolean(o.hq)]),
  (v?.clips || []).slice(0, 20).map((c) => [c.clip_id, c.status]),
  v?.dir_error ?? null,
]);

export function createClipBridge({
  ipcMain,
  BrowserWindow,
  isHiddenWindow = () => false,
  service = () => null,
  apiBase,
  apiKey = () => '',
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  timers = globalThis,
  intervalMs = CLIP_REPORT_MS,
}) {
  let view = null;
  let lastKey = null;
  let lastPost = -Infinity;
  let inFlight = false;
  let lastFailLog = -Infinity;

  const isDeskContents = (contents) => {
    try {
      const win = BrowserWindow.fromWebContents(contents);
      return Boolean(win) && !win.isDestroyed() && !isHiddenWindow(win) && DESK_URL.test(String(contents.getURL() || ''));
    } catch {
      return false; // a window closing mid-read is no desk window
    }
  };
  const deskContents = () =>
    BrowserWindow.getAllWindows()
      .filter((w) => !w.isDestroyed() && !isHiddenWindow(w))
      .map((w) => w.webContents)
      .filter((c) => !c.isDestroyed() && isDeskContents(c));

  ipcMain.handle(CLIPS_SUBSCRIBE_CHANNEL, () => view);
  ipcMain.handle(CLIPS_ACT_CHANNEL, async (event, request) => {
    if (!isDeskContents(event.sender)) return { ok: false, reason: 'CLIP_FORBIDDEN', error: 'Clips answer the desk windows only.' };
    const svc = service();
    if (!svc) return { ok: false, reason: 'CLIP_UNAVAILABLE', error: 'Clips are not running in this desk.' };
    return svc.act(request);
  });
  const onTab = (event, report) => {
    if (!isDeskContents(event.sender)) return;
    service()?.tabReport(BrowserWindow.fromWebContents(event.sender), report);
  };
  ipcMain.on(CLIPS_TAB_CHANNEL, onTab);

  const noteFailure = (why) => {
    const t = now();
    if (t - lastFailLog < REPORT_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[nova] clip status not delivered to the backend', why);
  };

  function post() {
    if (!view || inFlight) return;
    lastPost = now();
    const headers = { 'Content-Type': 'application/json' };
    const key = apiKey();
    if (key) headers[NOVA_API_KEY_HEADER] = key;
    inFlight = true;
    // The backend keeps a summary: at most 50 clips of the list.
    const body = JSON.stringify({ ...view, clips: (view.clips || []).slice(0, 50) });
    try {
      Promise.resolve(fetchImpl(`${apiBase}${CLIPS_REPORT_PATH}`, { method: 'POST', headers, body, signal: AbortSignal.timeout(intervalMs) }))
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
      for (const contents of deskContents()) contents.send(CLIPS_VIEW_CHANNEL, view);
      const key = shapeKey(next);
      if (key !== lastKey || now() - lastPost >= intervalMs) {
        lastKey = key;
        post();
      }
    },
    view: () => view,
    stop() {
      timers.clearInterval(timer);
      ipcMain.removeHandler?.(CLIPS_SUBSCRIBE_CHANNEL);
      ipcMain.removeHandler?.(CLIPS_ACT_CHANNEL);
      ipcMain.removeListener(CLIPS_TAB_CHANNEL, onTab);
    },
  };
}
