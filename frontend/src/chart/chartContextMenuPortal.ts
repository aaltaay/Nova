/**
 * Where the chart menu portals to.
 *
 * Normally `<body>`, so the pane cannot clip it. While the pane header's
 * fullscreen control (#117) has that chart in browser fullscreen, only the
 * fullscreen element's subtree paints -- a menu left in `<body>` would open
 * invisibly. Portal inside the fullscreen element in that case.
 */
import { fullscreenElement } from './chartFullscreen';

export function chartContextMenuPortalTarget(
  container: Element | null,
): HTMLElement | null {
  if (typeof document === 'undefined') return null;
  const active = fullscreenElement();
  if (active instanceof HTMLElement && container && active.contains(container)) {
    return active;
  }
  return document.body;
}
