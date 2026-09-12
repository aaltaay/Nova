/**
 * Browser/OS fullscreen for a chart host. Double-click grid maximize is a
 * separate path -- this module never changes ChartGrid layout.
 */

type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void> | void;
};

type FullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void> | void;
};

let chartFullscreenActive = false;
let escapeConsumedForFullscreen = false;

export function fullscreenElement(): Element | null {
  const doc = document as FullscreenDocument;
  return document.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

export function getChartFullscreenActive(): boolean {
  return chartFullscreenActive || !!fullscreenElement();
}

export function markChartFullscreen(active: boolean): void {
  chartFullscreenActive = active;
}

export function isChartFullscreen(el: Element | null): boolean {
  if (!el) return false;
  const current = fullscreenElement();
  return current === el || (!!current && (el.contains(current) || current.contains(el)));
}

export async function requestChartFullscreen(el: HTMLElement): Promise<void> {
  const node = el as FullscreenElement;
  const req = node.requestFullscreen?.bind(node) ?? node.webkitRequestFullscreen?.bind(node);
  if (!req) return;
  if (isChartFullscreen(el)) return;
  const current = fullscreenElement();
  if (current && current !== el) {
    await exitChartFullscreen();
  }
  await Promise.resolve(req());
  markChartFullscreen(true);
}

export async function exitChartFullscreen(): Promise<void> {
  if (!fullscreenElement()) {
    markChartFullscreen(false);
    return;
  }
  const doc = document as FullscreenDocument;
  const exit = document.exitFullscreen?.bind(document) ?? doc.webkitExitFullscreen?.bind(document);
  if (!exit) return;
  await Promise.resolve(exit());
}

export async function toggleChartFullscreen(el: HTMLElement): Promise<void> {
  if (isChartFullscreen(el)) await exitChartFullscreen();
  else await requestChartFullscreen(el);
}

/** Call from the chart Esc handler before grid restore can run. */
export function consumeEscapeForFullscreen(): boolean {
  if (!getChartFullscreenActive()) return false;
  escapeConsumedForFullscreen = true;
  return true;
}

export function takeEscapeConsumedForFullscreen(): boolean {
  const taken = escapeConsumedForFullscreen;
  escapeConsumedForFullscreen = false;
  return taken;
}

/** Grid Esc must not unwind #113 maximize while leaving (or just leaving) FS. */
export function shouldRestoreGridOnEscape(
  event: { key: string },
  activeTool: string | null,
): boolean {
  if (event.key !== 'Escape') return false;
  if (takeEscapeConsumedForFullscreen() || getChartFullscreenActive()) return false;
  if (activeTool) return false;
  return true;
}
