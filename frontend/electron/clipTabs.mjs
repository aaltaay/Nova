/**
 * Share clips (ADR 039): where every Trader tab is. Each desk window reports
 * what its Trader view shows (frontend/src/clips/clipTabReport.ts: the active
 * symbol, whether it is on screen, the tab's and its panels' rectangles in
 * CSS pixels); this module adds where the window's page sits on the screen
 * (getContentBounds, DIP) and whether it is minimized, and keeps the last
 * `CLIP_TAB_HISTORY_SEC` of changes in memory so "save the last 5 min" knows
 * where a tab was before anyone pressed anything. Nothing here is persisted.
 */
import { CLIP_PANELS, CLIP_TAB_HISTORY_SEC, cleanSymbol, readRect } from './clipPlan.mjs';

export const CLIP_TAB_REASONS = Object.freeze(['page', 'document', 'draft', 'sample']);
const round = (r) => (r ? { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.w), h: Math.round(r.h) } : null);

/** A tab report checked once; null when it cannot be read. */
export function readTabReport(raw) {
  if (!raw || typeof raw !== 'object' || raw.schema_version !== 1) return null;
  const windowId = typeof raw.window_id === 'string' ? raw.window_id.slice(0, 64) : null;
  const inner = raw.inner && raw.inner.w > 0 && raw.inner.h > 0 ? { w: Number(raw.inner.w), h: Number(raw.inner.h) } : null;
  if (!windowId || !inner) return null;
  const panels = {};
  for (const id of CLIP_PANELS) {
    const r = readRect(raw.panels?.[id]);
    if (r) panels[id] = round(r);
  }
  return {
    windowId,
    visible: raw.visible === true,
    reason: CLIP_TAB_REASONS.includes(raw.reason) ? raw.reason : null,
    symbol: cleanSymbol(raw.symbol),
    pane: round(readRect(raw.pane)),
    panels,
    inner,
  };
}

/** A tab's geometry as a clip mark carries it (AGENTS.md §3), or null without a rectangle. */
export function geometryOf(entry) {
  if (!entry?.pane || !entry.content) return null;
  return {
    window_id: entry.windowId,
    display_id: entry.displayId,
    content: { ...entry.content },
    inner: { ...entry.inner },
    pane: { ...entry.pane },
    panels: { ...entry.panels },
  };
}

export const geometryKey = (g) => (g ? JSON.stringify([g.window_id, g.display_id, g.content, g.inner, g.pane, g.panels]) : '');

/**
 * Where `symbol`'s tab is in `entries`: shown in a window (the one it was
 * last shown in first), else why not -- `minimized`, `closed`, `symbol` (the
 * tab shows another symbol: `showing`), `page` / `document` (the Trader view
 * is off screen) or `not_open` (no window has a tab for it).
 */
export function stateFor(symbol, entries, preferWindowId = null) {
  const shown = entries.filter((e) => e.symbol === symbol && e.visible && !e.minimized && e.pane);
  const pick = shown.find((e) => e.windowId === preferWindowId) ?? shown[0];
  if (pick) return { shown: true, windowId: pick.windowId, geometry: geometryOf(pick) };
  const last = preferWindowId ? entries.find((e) => e.windowId === preferWindowId) : null;
  if (!last) {
    const anywhere = entries.find((e) => e.symbol === symbol);
    if (!anywhere) return { shown: false, windowId: preferWindowId, reason: preferWindowId ? 'closed' : 'not_open', showing: null };
    return { shown: false, windowId: anywhere.windowId, reason: anywhere.minimized ? 'minimized' : anywhere.reason ?? 'page', showing: null };
  }
  if (last.minimized) return { shown: false, windowId: last.windowId, reason: 'minimized', showing: null };
  if (last.visible && last.symbol && last.symbol !== symbol) return { shown: false, windowId: last.windowId, reason: 'symbol', showing: last.symbol };
  return { shown: false, windowId: last.windowId, reason: last.reason ?? 'page', showing: null };
}

export const stateKey = (s) => JSON.stringify([s.shown, s.windowId, s.reason ?? null, s.showing ?? null, geometryKey(s.geometry)]);

export function createTabTracker({ screen, now = () => Date.now(), historySec = CLIP_TAB_HISTORY_SEC }) {
  const entries = new Map(); // webContents id -> entry
  const history = []; // {ts, entries: [...]} snapshots, oldest first

  function place(entry, win) {
    try {
      const b = win.getContentBounds();
      entry.content = { x: b.x, y: b.y, width: b.width, height: b.height };
      entry.minimized = win.isMinimized();
      const d = screen.getDisplayMatching?.(b);
      entry.displayId = d ? String(d.id) : null;
    } catch {
      entry.content = null; // the window is closing: it has no place any more
    }
  }

  function snapshot() {
    const t = now() / 1000;
    history.push({ ts: t, entries: [...entries.values()].map((e) => ({ ...e, win: undefined })) });
    const cut = t - historySec;
    while (history.length > 1 && history[1].ts <= cut) history.shift();
  }

  return {
    /** Take a window's report; returns true when anything changed. */
    report(win, raw) {
      const r = readTabReport(raw);
      if (!r || !win) return false;
      const id = win.webContents.id;
      const prev = entries.get(id);
      const entry = { ...(prev ?? {}), ...r, win, updatedAt: now() };
      place(entry, win);
      entries.set(id, entry);
      const changed = !prev || stateKeyOf(prev) !== stateKeyOf(entry);
      if (changed) snapshot();
      return changed;
    },
    /** The window moved, resized, minimized or came back: its place is read again. */
    refresh(win) {
      const entry = entries.get(win?.webContents?.id);
      if (!entry) return false;
      const before = stateKeyOf(entry);
      place(entry, win);
      const changed = before !== stateKeyOf(entry);
      if (changed) snapshot();
      return changed;
    },
    forget(webContentsId) {
      if (entries.delete(webContentsId)) snapshot();
    },
    entries: () => [...entries.values()],
    windowOf: (windowId) => [...entries.values()].find((e) => e.windowId === windowId)?.win ?? null,
    stateFor: (symbol, preferWindowId) => stateFor(symbol, [...entries.values()], preferWindowId),
    /**
     * `symbol`'s states from `fromTs` to now, `[{ts, shown, windowId, reason,
     * showing, geometry}]`, one per change; the first is the state at `fromTs`.
     */
    historyFor(symbol, fromTs) {
      const out = [];
      let prefer = null;
      let key = null;
      for (const snap of history) {
        const s = stateFor(symbol, snap.entries, prefer);
        if (s.shown) prefer = s.windowId;
        const k = stateKey(s);
        if (k === key) continue;
        key = k;
        // Every state before `fromTs` folds into the one at `fromTs`; two at one moment keep the later.
        const ts = Math.max(snap.ts, fromTs);
        if (out.length && out[out.length - 1].ts >= ts) out.pop();
        out.push({ ts, ...s });
      }
      return out;
    },
  };
}

function stateKeyOf(e) {
  return JSON.stringify([e.windowId, e.visible, e.reason, e.symbol, e.pane, e.panels, e.inner, e.content, e.minimized, e.displayId]);
}
