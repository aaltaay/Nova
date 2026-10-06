/**
 * Whose view a chart pane shows (operator report 2026-10-06: "As I was zooming in and watching the chart, all
 * of a sudden it resized itself randomly ... We fixed it before"). A pane starts with Nova's view: the first
 * paint's window, kept at the live edge as bars arrive. Once the operator zooms or pans it -- the wheel, a drag
 * on the candles or the time axis, a pinch -- the view is theirs, and nothing Nova does on its own may move it
 * again: framing a newly leading setup, making room for the plan. What the operator asks for still moves it
 * (the plan's badge, "Show on chart", Reset chart), and a first paint -- another symbol, another timeframe, a
 * Sim seek -- or Reset chart hands the view back. In memory, per chart; nothing is persisted.
 *
 * lightweight-charts reports a range change without saying who made it, and fires it lazily (when the range is
 * next read, often on the next frame), so a change counts as the operator's when it comes while a press that
 * began on the chart is held, or within `OPERATOR_VIEW_SETTLE_MS` of a wheel or a release. A move of Nova's that
 * happens to land then counts as the operator's: the error only ever keeps the view where it is.
 */
import type { IChartApi } from 'lightweight-charts';

/** A range change this soon after a wheel or a release on the chart is that gesture's. */
export const OPERATOR_VIEW_SETTLE_MS = 300;

interface ViewWatch {
  owned: boolean;
}

const watches = new WeakMap<IChartApi, ViewWatch>();

/** Watch one chart for the operator's own zoom and pan; returns the cleanup. */
export function watchOperatorView(chart: IChartApi, now: () => number = () => performance.now()): () => void {
  const watch: ViewWatch = { owned: false };
  watches.set(chart, watch);
  const element = chart.chartElement();
  const view = element.ownerDocument.defaultView;
  let pressed = false;
  let settleUntil = -Infinity;
  const settle = () => {
    settleUntil = now() + OPERATOR_VIEW_SETTLE_MS;
  };
  const onDown = () => {
    pressed = true;
  };
  const onUp = () => {
    if (!pressed) return;
    pressed = false;
    settle();
  };
  const onRange = () => {
    if (pressed || now() <= settleUntil) watch.owned = true;
  };
  const capture = { capture: true, passive: true } as const;
  element.addEventListener('wheel', settle, capture);
  element.addEventListener('pointerdown', onDown, capture);
  view?.addEventListener('pointerup', onUp, capture);
  view?.addEventListener('pointercancel', onUp, capture);
  chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
  return () => {
    element.removeEventListener('wheel', settle, capture);
    element.removeEventListener('pointerdown', onDown, capture);
    view?.removeEventListener('pointerup', onUp, capture);
    view?.removeEventListener('pointercancel', onUp, capture);
    try {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
    } catch {
      /* the chart is already removed */
    }
    if (watches.get(chart) === watch) watches.delete(chart);
  };
}

/** True once the operator has zoomed or panned this chart and Nova has not been handed the view back. */
export function operatorOwnsView(chart: IChartApi | null): boolean {
  return !!chart && watches.get(chart)?.owned === true;
}

/** The view is Nova's again: a first paint or Reset chart put it back. */
export function releaseView(chart: IChartApi | null): void {
  const watch = chart ? watches.get(chart) : undefined;
  if (watch) watch.owned = false;
}
