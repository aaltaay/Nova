/**
 * Share clips (ADR 039): this window's Trader tab, for the main process --
 * the active symbol, whether its tab is on screen, and the tab's and its
 * panels' rectangles in CSS pixels. The main process adds where the window is
 * (electron/clipTabs.mjs), marks it on open clips, and keeps the last half
 * hour so "save the last 5 min" knows where the tab was. Reported on every
 * change and every CLIP_TAB_REPORT_MS; nothing is sent without the desktop app.
 */
import { useEffect, type RefObject } from 'react';
import { perfWindowIdentity } from '../perf/perfReporter';
import { CLIP_PANEL_SELECTORS, CLIP_TAB_REPORT_MS, type ClipPanelId } from './clipsConstants';
import { clipsBridge, reportClipTab } from './clipsStore';

type Rect = { x: number; y: number; w: number; h: number };
const rectOf = (el: Element): Rect | null => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 ? { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) } : null;
};

/** The box around every rectangle shown (a panel of several parts); null when none is. */
function unionOf(rects: (Rect | null)[]): Rect | null {
  const shown = rects.filter((r): r is Rect => r !== null);
  if (!shown.length) return null;
  const x = Math.min(...shown.map((r) => r.x));
  const y = Math.min(...shown.map((r) => r.y));
  return { x, y, w: Math.max(...shown.map((r) => r.x + r.w)) - x, h: Math.max(...shown.map((r) => r.y + r.h)) - y };
}

/** The pane of `symbol`'s Trader tab under `root`. */
export function paneFor(root: ParentNode | null, symbol: string | null): Element | null {
  if (!root || !symbol) return null;
  // Inside a quoted attribute value only a quote or a backslash needs escaping.
  return root.querySelector(`[data-testid="sv-tab-pane-${symbol.replace(/["\\]/g, '\\$&')}"]`);
}

/** One report (AGENTS.md §3 "Share clips": the tab report). */
export function buildClipTabReport({ windowId, symbol, onScreen, root, doc = document, win = window }: {
  windowId: string;
  symbol: string | null;
  onScreen: boolean;
  root: ParentNode | null;
  doc?: Document;
  win?: Window;
}): Record<string, unknown> {
  const docVisible = doc.visibilityState === 'visible';
  const pane = paneFor(root, symbol);
  const paneRect = pane ? rectOf(pane) : null;
  const visible = Boolean(symbol) && onScreen && docVisible && paneRect !== null;
  const panels: Partial<Record<ClipPanelId, Rect>> = {};
  if (pane && visible) {
    for (const [id, selector] of Object.entries(CLIP_PANEL_SELECTORS) as [ClipPanelId, string][]) {
      const r = unionOf([...pane.querySelectorAll(selector)].map(rectOf));
      if (r) panels[id] = r;
    }
  }
  return {
    schema_version: 1,
    window_id: windowId,
    visible,
    reason: !symbol ? 'draft' : !docVisible ? 'document' : !onScreen || !paneRect ? 'page' : null,
    symbol,
    pane: visible ? paneRect : null,
    panels,
    inner: { w: win.innerWidth, h: win.innerHeight },
  };
}

/**
 * Report this window's active Trader tab while it lives. `rootRef` holds the
 * Trader view (its panes are `sv-tab-pane-<SYMBOL>`); `symbol` is the active
 * tab's (null for a draft); `onScreen` whether the Trader view shows.
 */
export function useClipTabReport({ symbol, onScreen, rootRef }: {
  symbol: string | null;
  onScreen: boolean;
  rootRef: RefObject<HTMLElement | null>;
}): void {
  useEffect(() => {
    if (!clipsBridge()) return undefined;
    const { windowId } = perfWindowIdentity(window);
    let last = '';
    let lastAt = 0;
    const send = () => {
      const report = buildClipTabReport({ windowId, symbol, onScreen, root: rootRef.current });
      const key = JSON.stringify(report);
      const now = Date.now();
      // The same report is sent again now and then, so the main process's history stays warm.
      if (key === last && now - lastAt < CLIP_TAB_REPORT_MS * 2.5) return;
      last = key;
      lastAt = now;
      reportClipTab(report);
    };
    send();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => send());
    const root = rootRef.current;
    if (observer && root) observer.observe(root);
    const pane = paneFor(root, symbol);
    if (observer && pane) observer.observe(pane);
    window.addEventListener('resize', send);
    document.addEventListener('visibilitychange', send);
    const timer = window.setInterval(send, CLIP_TAB_REPORT_MS);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', send);
      document.removeEventListener('visibilitychange', send);
      window.clearInterval(timer);
      // Leaving: the tab is not on screen from here (a closed window says so itself).
      reportClipTab(buildClipTabReport({ windowId, symbol, onScreen: false, root: null }));
    };
  }, [symbol, onScreen, rootRef]);
}
